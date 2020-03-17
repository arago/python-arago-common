#!/usr/bin/env python3

import pkgutil
import os
import sys
import inspect
import random
import logging
import json
import time
import zipfile

logger = logging.getLogger(__name__)


class Plugin(object):
    """Base class that each plugin must inherit from. within this class
    you must define the methods that all of your plugins must implement
    """

    def __init__(self):
        self.description = 'UNKNOWN'

    def get_argument(self, issue, argument):
        a = issue.get(argument, [])
        return a if isinstance(a, list) else [a]

    def test(self, argument):
        """The method that we expect all plugins to implement. This is the
        method that will test if the plugin matches
        """
        raise NotImplementedError
        # return False

    def process(self, argument, context):
        """The method that we expect all plugins to implement. This is the
        method that our framework will call
        """
        raise NotImplementedError

class Processor(object):
    """Upon creation, this class will read the plugins package for modules
    that contain a class definition that is inheriting from the Plugin class
    """

    def __init__(self, plugin_package, pathname, ds, auto_reward, zip_file=None):
        """Constructor that initiates the reading of all available plugins
        when an instance of the PluginCollection object is created
        """
        self.pathname = pathname
        self.plugin_package = plugin_package
        self.zip_file = zip_file
        self.reload_plugins()
        self.ds = ds
        self.auto_reward = auto_reward

    def reload_plugins(self):
        """Reset the list of all plugins and initiate the walk over the main
        provided plugin package to load all available plugins
        """
        self.plugins = {}
        self.seen_paths = []
        logger.debug(" Looking for plugins under package '{}'".format(self.plugin_package))
        self.walk_package(self.plugin_package, self.plugins, 'root')
        logger.debug(" Found plugins '{}'".format(self.plugins))

    def decide_on_plugin(self, issue, possible):
        plugin = possible[0]
        if self.ds:
            possible_kis = [type(x).__name__+':'+str(y) for x, y in possible]
            data = {'Data': issue, 'PossibleKIs': possible_kis}
            decision = self.ds.decide(data)
            best_plugin, best_context = decision.split(':')
            plugin = [(x, y) for x, y in possible if type(x).__name__ == best_plugin and str(y) == best_context][0]
        return plugin

    def process_issue(self, issue):
        self.apply_all_plugins_on_value(issue)
        if self.ds:
            self.ds.finish_episode(issue)

    def apply_all_plugins_on_value(self, issue):
        "Apply all of the plugins on the issue supplied to this function"
        dirs = dict(enumerate(sorted(self.plugins)))
        dirs_lookup = {v: k for k, v in dirs.items()}
        current_dirno = 0
        issue['_reward'] = 0
        while current_dirno < len(dirs):
            directory = issue['_current_phase'] = dirs[current_dirno]
            logger.debug(" Phase '{}'".format(directory))
            subplugins = list(self.plugins[directory])
            any_executed = []
            while True:
                len_already_executed = len(any_executed)
                possible = self.test_plugins_on_value(issue, subplugins)
                for a in any_executed:
                    if a in possible:
                        possible.remove(a)
                if len(possible) < 1:
                    logger.debug(" No possible contexts in phase '{}'".format(directory))
                    break
                if directory.endswith('-parallel'):
                    for p in possible:
                        self.execute_plugin_with_context(issue, p[0], p[1])
                        any_executed.append(p)
                elif directory.endswith('-alternative'):
                    p = self.decide_on_plugin(issue, possible)
                    self.execute_plugin_with_context(issue, p[0], p[1])
                    break
                else:
                    p = possible.pop()
                    self.execute_plugin_with_context(issue, p[0], p[1])
                    any_executed.append(p)

                if issue['_current_phase'] != directory:
                    break
                if len(any_executed) == len_already_executed:
                    break
            issue['_reward'] += self.auto_reward
            if issue['_current_phase'] == directory:
                current_dirno += 1
            else:
                current_dirno = dirs_lookup.get(issue['_current_phase'], current_dirno+1)

    def execute_plugin_with_context(self, issue, plugin, context):
        logger.debug(" Executing context '{}' on '{}'".format(context, plugin.description))
        try:
            plugin.process(issue, context)
        except Exception as e:
            logger.warning(" Exception {} during execution of plugin {} with context {}".format(
                e, plugin.description, context))

    def test_plugins_on_value(self, issue, plugins):
        "Check plugins on the argument supplied to this function for test condition"
        passed_test_plugins = []
        logger.debug(" Test plugins for possible context")
        for plugin in plugins:
            try:
                contexts = plugin.test(issue)
                if contexts:
                    if isinstance(contexts, list):
                        for cntxt in contexts:
                            passed_test_plugins.append((plugin, cntxt))
                    else:
                        passed_test_plugins.append((plugin, contexts))
            except Exception as e:
                logger.warning(" Exception {} during context test of plugin {}".format(e, plugin.description))
        return passed_test_plugins

    def walk_package(self, package, root_pkg, child_pkg):
        "Recursively walk the supplied package to retrieve all plugins"
        imported_package = __import__(package, fromlist=[''])
        tmp = []
        for _, pluginname, ispkg in pkgutil.iter_modules(imported_package.__path__, imported_package.__name__ + '.'):
            if not ispkg:
                plugin_module = __import__(pluginname, fromlist=[''])
                clsmembers = inspect.getmembers(plugin_module, inspect.isclass)

                for (_, c) in clsmembers:
                    # Only add classes that are a sub class of Plugin, but NOT Plugin itself
                    if issubclass(c, Plugin) & (c is not Plugin):
                        logger.debug(" Found plugin class: {}.{}".format(c.__module__, c.__name__))
                        c.pathname = self.pathname
                        tmp.append(c())
        if len(tmp) > 0:
            root_pkg[child_pkg] = list(tmp)

        # Now that we have looked at all the modules in the current package, start looking
        # recursively for additional modules in sub packages
        all_current_paths = []
        if isinstance(imported_package.__path__, str):
            all_current_paths.append(imported_package.__path__)
        else:
            all_current_paths.extend([x for x in imported_package.__path__])

        for pkg_path in all_current_paths:
            if pkg_path not in self.seen_paths:
                self.seen_paths.append(pkg_path)

                # Get all subdirectory of the current package path directory
                if self.zip_file:
                    z = zipfile.ZipFile(self.zip_file)
                    dirs = list(set(os.path.dirname(x) for x in z.namelist() if x.startswith(package)))
                    child_pkgs = [x[len(package)+1:].replace('/','.') for x in dirs if x.strip() != package]
                else:
                    child_pkgs = [p for p in os.listdir(pkg_path) if os.path.isdir(os.path.join(pkg_path, p))]
                child_pkgs.sort()
                # For each subdirectory, apply the walk_package method recursively

                for child_pkg in child_pkgs:
                    if not child_pkg.startswith('__pycache__'):
                        self.walk_package(package + '.' + child_pkg, root_pkg, child_pkg)
