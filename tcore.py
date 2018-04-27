#!/usr/bin/python3

import argparse
import re
import sys
import os
import logging
import coloredlogs
import subprocess
import requests
import stat
import json
import shutil
import tabulate

# ------------------------------------------------------------------------------
# Common vars

CORE_INSTALL_DIR        = os.path.expanduser('~/.theCore/')
CORE_SRC_DIR            = CORE_INSTALL_DIR + 'theCore/'
CORE_TOOLCHAIN_DIR      = CORE_SRC_DIR + 'toolchains/'
CORE_INSTALLFILE        = CORE_INSTALL_DIR + 'installfile.json'
CORE_UPSTREAM           = 'https://github.com/forGGe/theCore'
CORE_THIRDPARTY_DIR     = CORE_INSTALL_DIR + 'thirdparties'
NIX_DIR                 = '/nix'
NIX_INSTALL_SCRIPT      = '/tmp/nix_install.sh'
NIX_SOURCE_FILE         = os.path.expanduser('~/.nix-profile/etc/profile.d/nix.sh')
CURRENT_RUNNING_DIR     = os.getcwd()
VERSION                 = '0.0.1'

# ------------------------------------------------------------------------------
# Logging

logger = logging.getLogger('tcore')
logger.setLevel(logging.DEBUG)

console_log = logging.StreamHandler()
console_log.setLevel(logging.DEBUG)

formatter = coloredlogs.ColoredFormatter('%(asctime)s [%(levelname)-8s] %(message)s')
console_log.setFormatter(formatter)

logger.addHandler(console_log)

# ------------------------------------------------------------------------------
# Utilities

# Runs command within the Nix environment
def run_with_nix(cmd):
    nix_cmd = '. {} && {}'.format(NIX_SOURCE_FILE, cmd)
    rc = subprocess.call(nix_cmd, shell = True)

    if rc != 0:
        logger.error('failed to run command: ' + nix_cmd)
        exit(1)

# Runs command within the Nix shell
def run_with_nix_shell(cmd):
    run_with_nix('nix-shell --run \"{}\" {}'.format(cmd, CORE_SRC_DIR))

# ------------------------------------------------------------------------------
# Commands

# Boostraps theCore, downloads and installs Nix
def do_bootstrap(args):
    if args.force:
        logger.warn('force (re)install theCore dev environment')

    # Check if nix exists

    if os.path.isdir(NIX_DIR) and not args.force:
        logger.info('Nix is already installed')
    else:
        logger.info('Installing Nix ... ')
        r = requests.get('https://nixos.org/nix/install')

        with open(NIX_INSTALL_SCRIPT, 'w') as fl:
            fl.write(r.text)

        os.chmod(NIX_INSTALL_SCRIPT, stat.S_IRWXU)
        rc = subprocess.call(NIX_INSTALL_SCRIPT, shell=True)

        if rc != 0:
            logger.error('failed to install Nix')
            exit(1)

    # Check if theCore is downloaded

    if os.path.isfile(CORE_INSTALLFILE) and not args.force:
        logger.info('theCore is already downloaded')
    else:
        if os.path.isdir(CORE_SRC_DIR):
            logger.info('remove old theCore files')
            shutil.rmtree(CORE_SRC_DIR)
        
        if os.path.isfile(CORE_INSTALLFILE):
            logger.info('remove theCore installfile')
            os.remove(CORE_INSTALLFILE)

        logger.info('downloading theCore')
        os.makedirs(CORE_SRC_DIR)
        run_with_nix('nix-env -i git')
        run_with_nix('git clone {} {}'.format(CORE_UPSTREAM, CORE_SRC_DIR))
        run_with_nix('cd {} && git submodule update --init --recursive'.format(CORE_SRC_DIR))

        # Initial install file contents
        installfile_content = { 'tcore_ver': VERSION }

        with open(CORE_INSTALLFILE, 'w') as installfile:
            installfile.write(json.dumps(installfile_content, indent=4) + '\n')

        # Initialize Nix (download all dependencies)
        run_with_nix_shell('true')

# Initializes empty project, or downloads existing one using Git.
def do_init(args):
    logger.warn('TODO: implement')

# Deletes Nix and theCore
def do_purge(args):
    logger.warn('TODO: implement')

# Compiles project specified in arguments
def do_compile(args):
    src_dir = os.path.normpath(args.source)
    metafile = src_dir + '/meta.json'

    logger.info('using source directory: ' + src_dir)
    logger.info('looking up for metafile: ' + metafile)

    if not os.path.isfile(metafile):
        logger.error('meta.json must be present in the project directory')
        exit(1)

    meta_cfg = {}

    with open(metafile, 'r') as fl:
        meta_cfg = json.load(fl)

    logger.info('compiling project: ' + meta_cfg['name'])

    if args.list_targets:
        targets = [ [ 'Target name', 'Configuration file', 'Description' ] ]
        # Only target list is requested, ignoring other operations
        for target in meta_cfg['targets']:
            targets.append([target['name'], target['config'], target['description']])    

        logger.info('\nSupported targets:\n' 
                + tabulate.tabulate(targets, tablefmt = "grid", headers = 'firstrow'))
        exit(0)
    elif not args.target:
        logger.error('target name must be specified.'
            + ' Use --list-targets for list of avaliable targets')
        exit(1)

    target_cfg = None

    for target in meta_cfg['targets']:
        if target['name'] == args.target:
            target_cfg = target
            break

    if not target_cfg:
        logger.error('no such target exists: ' + args.target)
        exit(1)

    # Build dir should be optional
    if args.builddir:
        build_dir = args.build_dir
    else:
        build_dir = src_dir + '/build/' + target_cfg['name']
        # In case of default values, build type must be appended
        if args.buildtype != 'none':
            build_dir = build_dir + '-' + args.buildtype

    # If special flag is set, build treated as host-oriented. No toolchain is 
    # required
    host_build = 'host' in target_cfg and not target_cfg['host']

    if not host_build:
        if os.path.isfile(src_dir + '/' + target_cfg['toolchain']):
            toolchain_path = src_dir + '/' + target_cfg['toolchain']
        else:
            toolchain_path = CORE_TOOLCHAIN_DIR + target_cfg['toolchain']
    
        if not os.path.isfile(toolchain_path):
            logger.error('no such toolchain found: ' + toolchain_path)

    # TODO: get default configuration from theCore, if any
    config_json_path = src_dir + '/' + target_cfg['config']

    if not os.path.isfile(config_json_path):
        logger.error('no such configuration file found: ' + config_json_path)

    # Remove directory is enough in CMake case
    if args.clean:
        logger.info('performing cleanup before build ' + build_dir)
        if os.path.isdir(build_dir):
            shutil.rmtree(build_dir)
        else:
            logger.info('nothing to clean')

    # To generate build files with CMake we must first step into 
    # the build  directory

    if not os.path.isdir(build_dir):
        os.makedirs(build_dir)

    os.chdir(build_dir)

    # 'none' means no build type specified
    if args.buildtype == 'none':
        cmake_build_type = ''
    elif args.buildtype == 'debug':
        cmake_build_type = '-DCMAKE_BUILD_TYPE=Debug'
    elif args.buildtype == 'release':
        cmake_build_type = '-DCMAKE_BUILD_TYPE=Release'
    elif args.buildtype == 'min_size':
        cmake_build_type = '-DCMAKE_BUILD_TYPE=MinSizeRel'

    if not host_build:
        cmake_toolchain = '-DCMAKE_TOOLCHAIN_FILE=' + toolchain_path
    else:
        cmake_toolchain = ''

    thecore_cfg_param = '-DTHECORE_TARGET_CONFIG_FILE=' + config_json_path
    thecore_thirdparty_param = '-DTHECORE_THIRDPARTY_DIR=' + CORE_THIRDPARTY_DIR
    thecore_dir_param = '-DCORE_DIR=' + CORE_SRC_DIR

    run_with_nix_shell('cmake {} {} {} {} {}'
        .format(thecore_dir_param, cmake_build_type, cmake_toolchain, thecore_cfg_param, src_dir))

    run_with_nix_shell('make')

# ------------------------------------------------------------------------------
# Command line parsing

parser = argparse.ArgumentParser(description = 'theCore framework CLI')
subparsers = parser.add_subparsers(help = 'theCore subcommands')

bootstrap_parser = subparsers.add_parser('bootstrap', 
    help = 'Installs theCore development environment')
bootstrap_parser.add_argument('-f', '--force', action = 'store_true', 
    help = 'Force (re)install theCore dev environment')
bootstrap_parser.set_defaults(handler = do_bootstrap)

purge_parser = subparsers.add_parser('purge', 
    help = 'Deletes theCore development environment')
purge_parser.set_defaults(handler = do_purge)

init_parser = subparsers.add_parser('init', 
    help = 'Initialize project based on theCore')
init_parser.add_argument('-r', '--remote', type = str, 
    help = 'Git remote to download project from')
init_parser.set_defaults(handler = do_init)

compile_parser = subparsers.add_parser('compile', 
    help = 'Build project')
compile_parser.add_argument('-s', '--source', type = str, 
    help = 'Path to the source code. Defaults to current directory.', 
    default = os.getcwd())
compile_parser.add_argument('-b', '--builddir', type = str, 
    help = 'Path to the build directory. Defaults to ./build/<target_name>-<build_type>,' 
            + ' where <target_name> is the selected target and <build_type> '
            + ' is a build type supplied with --buildtype parameter')
compile_parser.add_argument('--buildtype', type = str, 
    help = 'Build type. Default is none',
    choices = [ 'debug', 'release', 'min_size', 'none' ], default = 'none')
compile_parser.add_argument('-t', '--target', type = str, 
    help = 'Target name to compile for')
compile_parser.add_argument('-l', '--list-targets', action = 'store_true', 
    help = 'List supported targets')
compile_parser.add_argument('-c', '--clean', action = 'store_true', 
    help = 'Clean build')
compile_parser.set_defaults(handler = do_compile)

args = parser.parse_args()

if args.handler:
    args.handler(args)
