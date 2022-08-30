#!/usr/bin/env python3
# coding=utf-8

#
# Copyright (c) 2022 Huawei Device Co., Ltd.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
import re
import zipfile
import stat
import time
import json
from dataclasses import dataclass
from tempfile import TemporaryDirectory
from tempfile import NamedTemporaryFile

from xdevice import ITestKit
from xdevice import platform_logger
from xdevice import Plugin
from xdevice import ParamError
from xdevice import get_file_absolute_path
from xdevice import get_config_value
from xdevice import exec_cmd
from xdevice import ConfigConst
from xdevice import AppInstallError
from xdevice import convert_serial
from xdevice import check_path_legal
from xdevice import modify_props
from xdevice import get_app_name_by_tool
from xdevice import remount
from xdevice import disable_keyguard
from xdevice import get_class

from ohos.constants import CKit
from ohos.environment.dmlib import CollectingOutputReceiver

__all__ = ["STSKit", "CommandKit", "PushKit", "PropertyCheckKit", "ShellKit", "WifiKit",
           "ConfigKit", "AppInstallKit", "ComponentKit",
           "junit_dex_para_parse", "oh_jsunit_para_parse"]

MAX_WAIT_COUNT = 4
TARGET_SDK_VERSION = 22

LOG = platform_logger("Kit")


@Plugin(type=Plugin.TEST_KIT, id=CKit.command)
class CommandKit(ITestKit):

    def __init__(self):
        self.run_command = []
        self.teardown_command = []
        self.paths = ""

    def __check_config__(self, config):
        self.paths = get_config_value('paths', config)
        self.teardown_command = get_config_value('teardown', config)
        self.run_command = get_config_value('shell', config)

    def __setup__(self, device, **kwargs):
        del kwargs
        LOG.debug("CommandKit setup, device:{}, params:{}".
                  format(device, self.get_plugin_config().__dict__))
        if len(self.run_command) == 0:
            LOG.info("No setup_command to run, skipping!")
            return
        for command in self.run_command:
            self._run_command(command, device)

    def __teardown__(self, device):
        LOG.debug("CommandKit teardown: device:{}, params:{}".format
                  (device, self.get_plugin_config().__dict__))
        if len(self.teardown_command) == 0:
            LOG.info("No teardown_command to run, skipping!")
            return
        for command in self.teardown_command:
            self._run_command(command, device)

    def _run_command(self, command, device):

        command_type = command.get("name").strip()
        command_value = command.get("value")

        if command_type == "reboot":
            device.reboot()
        elif command_type == "install":
            LOG.debug("Trying to install package {}".format(command_value))
            package = get_file_absolute_path(command_value, self.paths)
            if not package or not os.path.exists(package):
                LOG.error(
                    "The package {} to be installed does not exist".format(
                        package))

            result = device.install_package(package)
            if not result.startswith("Success"):
                raise AppInstallError(
                    "Failed to install %s on %s. Reason:%s" %
                    (package, device.__get_serial__(), result))
            LOG.debug("Installed package finished {}".format(package))
        elif command_type == "uninstall":
            LOG.debug("Trying to uninstall package {}".format(command_value))
            package = get_file_absolute_path(command_value, self.paths)
            app_name = get_app_name_by_tool(package, self.paths)
            if app_name:
                result = device.uninstall_package(app_name)
                if not result.startswith("Success"):
                    LOG.error("error uninstalling package %s %s" %
                              (device.__get_serial__(), result))
            LOG.debug("uninstall package finished {}".format(app_name))
        elif command_type == "pull":
            files = command_value.split("->")
            remote = files[0].strip()
            local = files[1].strip()
            device.pull_file(remote, local)
        elif command_type == "push":
            files = command_value.split("->")
            src = files[0].strip()
            dst = files[1].strip() if files[1].strip().startswith("/") else \
                files[1].strip() + Props.dest_root
            LOG.debug(
                "Trying to push the file local {} to remote{}".format(
                    src, dst))
            real_src_path = get_file_absolute_path(src, self.paths)
            if not real_src_path or not os.path.exists(real_src_path):
                LOG.error(
                    "The src file {} to be pushed does not exist".format(src))
            device.push_file(real_src_path, dst)
            LOG.debug("Push file finished from {} to {}".format(src, dst))
        elif command_type == "shell":
            device.execute_shell_command(command_value)


@Plugin(type=Plugin.TEST_KIT, id=CKit.sts)
class STSKit(ITestKit):
    def __init__(self):
        self.sts_version = ""
        self.throw_error = ""

    def __check_config__(self, config):
        self.sts_version = get_config_value('sts-version', config)
        self.throw_error = get_config_value('throw-error', config)
        if len(self.sts_version) < 1:
            raise TypeError(
                "The sts_version: {} is invalid".format(self.sts_version))

    def __setup__(self, device, **kwargs):
        del kwargs
        LOG.debug("STSKit setup, device:{}, params:{}".
                  format(device, self.get_plugin_config().__dict__))
        device_spl = device.get_property(Props.security_patch)
        if device_spl is None or device_spl == "":
            LOG.error("The device security {} is invalid".format(device_spl))
            raise ParamError(
                "The device security patch version {} is invalid".format(
                    device_spl))
        rex = '^[a-zA-Z\\d\\.]+_([\\d]+-[\\d]+)$'
        match = re.match(rex, self.sts_version)
        if match is None:
            LOG.error("The sts version {} does match the rule".format(
                self.sts_version))
            raise ParamError("The sts version {} does match the rule".format(
                self.sts_version))
        sts_version_date_user = match.group(1).join("-01")
        sts_version_date_kernel = match.group(1).join("-05")
        if device_spl in [sts_version_date_user, sts_version_date_kernel]:
            LOG.info(
                "The device SPL version {} match the sts version {}".format(
                    device_spl, self.sts_version))
        else:
            err_msg = "The device SPL version {} does not match the sts " \
                      "version {}".format(device_spl, self.sts_version)
            LOG.error(err_msg)
            raise ParamError(err_msg)

    def __teardown__(self, device):
        LOG.debug("STSKit teardown: device:{}, params:{}".format
                  (device, self.get_plugin_config().__dict__))


@Plugin(type=Plugin.TEST_KIT, id=CKit.push)
class PushKit(ITestKit):
    def __init__(self):
        self.pre_push = ""
        self.push_list = ""
        self.post_push = ""
        self.is_uninstall = ""
        self.paths = ""
        self.pushed_file = []
        self.abort_on_push_failure = True
        self.teardown_push = ""

    def __check_config__(self, config):
        self.pre_push = get_config_value('pre-push', config)
        self.push_list = get_config_value('push', config)
        self.post_push = get_config_value('post-push', config)
        self.teardown_push = get_config_value('teardown-push', config)
        self.is_uninstall = get_config_value('uninstall', config,
                                             is_list=False, default=True)
        self.abort_on_push_failure = get_config_value(
            'abort-on-push-failure', config, is_list=False, default=True)
        if isinstance(self.abort_on_push_failure, str):
            self.abort_on_push_failure = False if \
                self.abort_on_push_failure.lower() == "false" else True

        self.paths = get_config_value('paths', config)
        self.pushed_file = []

    def __setup__(self, device, **kwargs):
        del kwargs
        LOG.debug("PushKit setup, device:{}".format(device.device_sn))
        for command in self.pre_push:
            run_command(device, command)
        dst = None
        for push_info in self.push_list:
            files = re.split('->|=>', push_info)
            if len(files) != 2:
                LOG.error("The push spec is invalid: {}".format(push_info))
                continue
            src = files[0].strip()
            dst = files[1].strip() if files[1].strip().startswith("/") else \
                files[1].strip() + Props.dest_root
            LOG.debug(
                "Trying to push the file local {} to remote {}".format(src,
                                                                       dst))

            try:
                real_src_path = get_file_absolute_path(src, self.paths)
            except ParamError as error:
                if self.abort_on_push_failure:
                    raise error
                else:
                    LOG.warning(error, error_no=error.error_no)
                    continue
            remount(device)
            # hdc don't support push directory now
            if os.path.isdir(real_src_path):
                device.connector_command("shell mkdir {}".format(dst))
                for root, _, files in os.walk(real_src_path):
                    for file in files:
                        device.push_file("{}".format(os.path.join(root, file)),
                                         "{}".format(dst))
                        LOG.debug(
                            "Push file finished from {} to {}".format(
                                os.path.join(root, file), dst))
                        self.pushed_file.append(os.path.join(dst, file))
            else:
                if device.is_directory(dst):
                    dst = os.path.join(dst, os.path.basename(real_src_path))
                    if dst.find("\\") > -1:
                        dst_paths = dst.split("\\")
                        dst = "/".join(dst_paths)
                device.push_file("{}".format(real_src_path),
                                 "{}".format(dst))
                LOG.debug("Push file finished from {} to {}".format(src, dst))
                self.pushed_file.append(dst)
        for command in self.post_push:
            run_command(device, command)
        return self.pushed_file, dst

    def add_pushed_dir(self, src, dst):
        for root, _, files in os.walk(src):
            for file_path in files:
                self.pushed_file.append(
                    os.path.join(root, file_path).replace(src, dst))

    def __teardown__(self, device):
        LOG.debug("PushKit teardown: device:{}".format(device.device_sn))
        for command in self.teardown_push:
            run_command(device, command)
        if self.is_uninstall:
            remount(device)
            for file_name in self.pushed_file:
                LOG.debug("Trying to remove file {}".format(file_name))
                file_name = file_name.replace("\\", "/")

                for _ in range(
                        Props.trying_remove_maximum_times):
                    collect_receiver = CollectingOutputReceiver()
                    file_name = check_path_legal(file_name)
                    device.execute_shell_command("rm -rf {}".format(
                        file_name), receiver=collect_receiver,
                        output_flag=False)
                    if not collect_receiver.output:
                        LOG.debug(
                            "Removed file {} successfully".format(file_name))
                        break
                    else:
                        LOG.error("Removed file {} successfully".
                                  format(collect_receiver.output))
                else:
                    LOG.error("Failed to remove file {}".format(file_name))

    def __add_pushed_file__(self, device, src, dst):
        if device.is_directory(dst):
            dst = dst + os.path.basename(src) if dst.endswith(
                "/") else dst + "/" + os.path.basename(src)
        self.pushed_file.append(dst)

    def __add_dir_pushed_files__(self, device, src, dst):
        if device.file_exist(device, dst):
            for _, dirs, files in os.walk(src):
                for file_path in files:
                    if dst.endswith("/"):
                        dst = "%s%s" % (dst, os.path.basename(file_path))
                    else:
                        dst = "%s/%s" % (dst, os.path.basename(file_path))
                    self.pushed_file.append(dst)
                for dir_name in dirs:
                    self.__add_dir_pushed_files__(device, dir_name, dst)
        else:
            self.pushed_file.append(dst)


@Plugin(type=Plugin.TEST_KIT, id=CKit.propertycheck)
class PropertyCheckKit(ITestKit):
    def __init__(self):
        self.prop_name = ""
        self.expected_value = ""
        self.throw_error = ""

    def __check_config__(self, config):
        self.prop_name = get_config_value('property-name', config,
                                          is_list=False)
        self.expected_value = get_config_value('expected-value', config,
                                               is_list=False)
        self.throw_error = get_config_value('throw-error', config,
                                            is_list=False)

    def __setup__(self, device, **kwargs):
        del kwargs
        LOG.debug("PropertyCheckKit setup, device:{}".format(device.device_sn))
        if not self.prop_name:
            LOG.warning("The option of property-name not setting")
            return
        prop_value = device.get_property(self.prop_name)
        if not prop_value:
            LOG.warning(
                "The property {} not found on device, cannot check the value".
                    format(self.prop_name))
            return

        if prop_value != self.expected_value:
            msg = "The value found for property {} is {}, not same with the " \
                  "expected {}".format(self.prop_name, prop_value,
                                       self.expected_value)
            LOG.warning(msg)
            if self.throw_error and self.throw_error.lower() == 'true':
                raise Exception(msg)

    @classmethod
    def __teardown__(cls, device):
        LOG.debug("PropertyCheckKit teardown: device:{}".format(
            device.device_sn))


@Plugin(type=Plugin.TEST_KIT, id=CKit.shell)
class ShellKit(ITestKit):
    def __init__(self):
        self.command_list = []
        self.tear_down_command = []
        self.paths = None

    def __check_config__(self, config):
        self.command_list = get_config_value('run-command', config)
        self.tear_down_command = get_config_value('teardown-command', config)
        self.paths = get_config_value('paths', config)

    def __setup__(self, device, **kwargs):
        del kwargs
        LOG.debug("ShellKit setup, device:{}".format(device.device_sn))
        if len(self.command_list) == 0:
            LOG.info("No setup_command to run, skipping!")
            return
        for command in self.command_list:
            run_command(device, command)

    def __teardown__(self, device):
        LOG.debug("ShellKit teardown: device:{}".format(device.device_sn))
        if len(self.tear_down_command) == 0:
            LOG.info("No teardown_command to run, skipping!")
            return
        for command in self.tear_down_command:
            run_command(device, command)


@Plugin(type=Plugin.TEST_KIT, id=CKit.wifi)
class WifiKit(ITestKit):
    def __init__(self):
        self.certfilename = ""
        self.certpassword = ""
        self.wifiname = ""
        self.paths = ""

    def __check_config__(self, config):
        self.certfilename = get_config_value(
            'certfilename', config, False,
            default=None)
        self.certpassword = get_config_value(
            'certpassword', config, False,
            default=None)
        self.wifiname = get_config_value(
            'wifiname', config, False,
            default=None)
        self.paths = get_config_value('paths', config)

    def __setup__(self, device, **kwargs):
        request = kwargs.get("request", None)
        if not request:
            LOG.error("WifiKit need input request")
            return
        testargs = request.get("testargs", {})
        self.certfilename = \
            testargs.pop("certfilename", [self.certfilename])[0]
        self.wifiname = \
            testargs.pop("wifiname", [self.wifiname])[0]
        self.certpassword = \
            testargs.pop("certpassword", [self.certpassword])[0]
        del kwargs
        LOG.debug("WifiKit setup, device:{}".format(device.device_sn))

        try:
            wifi_app_path = get_file_absolute_path(
                Props.Paths.service_wifi_app_path, self.paths)
        except ParamError as _:
            wifi_app_path = None

        if wifi_app_path is None:
            LOG.error("The resource wifi app file does not exist!")
            return

        try:
            pfx_path = get_file_absolute_path(
                "tools/wifi/%s" % self.certfilename
            ) if self.certfilename else None
        except ParamError as _:
            pfx_path = None

        if pfx_path is None:
            LOG.error("The resource wifi pfx file does not exist!")
            return
        pfx_dest_path = \
            "/storage/emulated/0/%s" % self.certfilename
        if self.wifiname is None:
            LOG.error("The wifi name is not given!")
            return
        if self.certpassword is None:
            LOG.error("The wifi password is not given!")
            return

        device.install_package(wifi_app_path, command="-r")
        device.push_file(pfx_path, pfx_dest_path)
        device.execute_shell_command("svc wifi enable")
        for _ in range(Props.maximum_connect_wifi_times):
            connect_wifi_cmd = Props.connect_wifi_cmd % (
                pfx_dest_path,
                self.certpassword,
                self.wifiname
            )
            if device.execute_shell_command(connect_wifi_cmd):
                LOG.info("Connect wifi successfully")
                break
        else:
            LOG.error("Connect wifi failed")

    @classmethod
    def __teardown__(cls, device):
        LOG.debug("WifiKit teardown: device:{}".format(device.device_sn))
        LOG.info("Disconnect wifi")
        device.execute_shell_command("svc wifi disable")


@dataclass
class Props:
    @dataclass
    class Paths:
        system_build_prop_path = "/%s/%s" % ("system", "build.prop")
        service_wifi_app_path = "tools/wifi/%s" % "Service-wifi.app"

    dest_root = "/%s/%s/" % ("data", "data")
    mnt_external_storage = "EXTERNAL_STORAGE"
    trying_remove_maximum_times = 3
    maximum_connect_wifi_times = 3
    connect_wifi_cmd = "am instrument -e request \"{module:Wifi, " \
                       "method:connectWifiByCertificate, params:{'certPath':" \
                       "'%s'," \
                       "'certPassword':'%s'," \
                       "'wifiName':'%s'}}\"  " \
                       "-w com.xdeviceservice.service/.MainInstrumentation"
    security_patch = "ro.build.version.security_patch"


@Plugin(type=Plugin.TEST_KIT, id=CKit.config)
class ConfigKit(ITestKit):
    def __init__(self):
        self.is_connect_wifi = ""
        self.is_disconnect_wifi = ""
        self.wifi_kit = WifiKit()
        self.min_external_store_space = ""
        self.is_disable_dialing = ""
        self.is_test_harness = ""
        self.is_audio_silent = ""
        self.is_disable_dalvik_verifier = ""
        self.build_prop_list = ""
        self.is_enable_hook = ""
        self.cust_prop_file = ""
        self.is_prop_changed = False
        self.local_system_prop_file = ""
        self.cust_props = ""
        self.is_reboot_delay = ""
        self.is_remount = ""
        self.local_cust_prop_file = {}

    def __check_config__(self, config):
        self.is_connect_wifi = get_config_value('connect-wifi', config,
                                                is_list=False, default=False)
        self.is_disconnect_wifi = get_config_value(
            'disconnect-wifi-after-test', config, is_list=False, default=True)
        self.wifi_kit = WifiKit()
        self.min_external_store_space = get_config_value(
            'min-external-store-space', config)
        self.is_disable_dialing = get_config_value('disable-dialing', config)
        self.is_test_harness = get_config_value('set-test-harness', config)
        self.is_audio_silent = get_config_value('audio-silent', config)
        self.is_disable_dalvik_verifier = get_config_value(
            'disable-dalvik-verifier', config)
        self.build_prop_list = get_config_value('build-prop', config)
        self.cust_prop_file = get_config_value('cust-prop-file', config)
        self.cust_props = get_config_value('cust-prop', config)
        self.is_enable_hook = get_config_value('enable-hook', config)
        self.is_reboot_delay = get_config_value('reboot-delay', config)
        self.is_remount = get_config_value('remount', config, default=True)
        self.local_system_prop_file = NamedTemporaryFile(prefix='build',
                                                         suffix='.prop',
                                                         delete=False).name

    def __setup__(self, device, **kwargs):
        del kwargs
        LOG.debug("ConfigKit setup, device:{}".format(device.device_sn))
        if self.is_remount:
            remount(device)
        self.is_prop_changed = self.modify_system_prop(device)
        self.is_prop_changed = self.modify_cust_prop(
            device) or self.is_prop_changed

        keep_screen_on(device)
        if self.is_enable_hook:
            pass
        if self.is_prop_changed:
            device.reboot()

    def __teardown__(self, device):
        LOG.debug("ConfigKit teardown: device:{}".format(device.device_sn))
        if self.is_remount:
            remount(device)
        if self.is_connect_wifi and self.is_disconnect_wifi:
            self.wifi_kit.__teardown__(device)
        if self.is_prop_changed:
            device.push_file(self.local_system_prop_file,
                             Props.Paths.system_build_prop_path)
            device.execute_shell_command(
                " ".join(["chmod 644", Props.Paths.system_build_prop_path]))
            os.remove(self.local_system_prop_file)

            for target_file, temp_file in self.local_cust_prop_file.items():
                device.push_file(temp_file, target_file)
                device.execute_shell_command(
                    " ".join(["chmod 644", target_file]))
                os.remove(temp_file)

    def modify_system_prop(self, device):
        prop_changed = False
        new_props = {}
        if self.is_disable_dialing:
            new_props['ro.telephony.disable-call'] = 'true'
        if self.is_test_harness:
            new_props['ro.monkey'] = '1'
            new_props['ro.test_harness'] = '1'
        if self.is_audio_silent:
            new_props['ro.audio.silent'] = '1'
        if self.is_disable_dalvik_verifier:
            new_props['dalvik.vm.dexopt-flags'] = 'v=n'
        for prop in self.build_prop_list:
            if prop is None or prop.find("=") < 0 or len(prop.split("=")) != 2:
                LOG.warning("The build prop:{} not match the format "
                            "'key=value'".format(prop))
                continue
            new_props[prop.split("=")[0]] = prop.split("=")[1]
        if new_props:
            prop_changed = modify_props(device, self.local_system_prop_file,
                                        Props.Paths.system_build_prop_path,
                                        new_props)
        return prop_changed

    def modify_cust_prop(self, device):
        prop_changed = False
        cust_files = {}
        new_props = {}
        for cust_prop_file in self.cust_prop_file:
            # the correct format should be "CustName:/cust/prop/absolutepath"
            if len(cust_prop_file.split(":")) != 2:
                LOG.error(
                    "The value %s of option cust-prop-file is incorrect" %
                    cust_prop_file)
                continue
            cust_files[cust_prop_file.split(":")[0]] = \
                cust_prop_file.split(":")[1]
        for prop in self.cust_props:
            # the correct format should be "CustName:key=value"
            prop_infos = re.split(r'[:|=]', prop)
            if len(prop_infos) != 3:
                LOG.error(
                    "The value {} of option cust-prop is incorrect".format(
                        prop))
                continue
            file_name, key, value = prop_infos
            if file_name not in cust_files:
                LOG.error(
                    "The custName {} must be in cust-prop-file option".format(
                        file_name))
                continue
            props = new_props.setdefault(file_name, {})
            props[key] = value

        for name in new_props.keys():
            cust_file = cust_files.get(name)
            temp_cust_file = NamedTemporaryFile(prefix='cust', suffix='.prop',
                                                delete=False).name
            self.local_cust_prop_file[cust_file] = temp_cust_file
            try:
                prop_changed = modify_props(device, temp_cust_file, cust_file,
                                            new_props[name]) or prop_changed
            except KeyError:
                LOG.error("Get props error.")
                continue

        return prop_changed


@Plugin(type=Plugin.TEST_KIT, id=CKit.app_install)
class AppInstallKit(ITestKit):
    def __init__(self):
        self.app_list = ""
        self.app_list_name = ""
        self.is_clean = ""
        self.alt_dir = ""
        self.ex_args = ""
        self.installed_app = set()
        self.paths = ""
        self.is_pri_app = ""
        self.pushed_hap_file = set()
        self.env_index_list = None

    def __check_config__(self, options):
        self.app_list = get_config_value('test-file-name', options)
        self.app_list_name = get_config_value('test-file-packName', options)
        self.is_clean = get_config_value('cleanup-apps', options, False)
        self.alt_dir = get_config_value('alt-dir', options, False)
        if self.alt_dir and self.alt_dir.startswith("resource/"):
            self.alt_dir = self.alt_dir[len("resource/"):]
        self.ex_args = get_config_value('install-arg', options)
        self.installed_app = set()
        self.paths = get_config_value('paths', options)
        self.is_pri_app = get_config_value('install-as-privapp', options,
                                           False, default=False)
        self.env_index_list = get_config_value('env-index', options)

    def __setup__(self, device, **kwargs):
        del kwargs
        LOG.debug("AppInstallKit setup, device:{}".format(device.device_sn))
        if len(self.app_list) == 0:
            LOG.info("No app to install, skipping!")
            return
        # to disable app install alert
        device.execute_shell_command("setprop persist.sys.platformautotest 1")
        for app in self.app_list:
            if self.alt_dir:
                app_file = get_file_absolute_path(app, self.paths,
                                                  self.alt_dir)
            else:
                app_file = get_file_absolute_path(app, self.paths)
            if app_file is None:
                LOG.error("The app file {} does not exist".format(app))
                continue
            if hasattr(device, "is_harmony") and device.is_harmony:
                device.connector_command("install \"{}\"".format(app_file))
            else:
                self.install_hap(device, app_file)
            self.installed_app.add(app_file)

    def __teardown__(self, device):
        LOG.debug("AppInstallKit teardown: device:{}".format(device.device_sn))
        if self.is_clean and str(self.is_clean).lower() == "true":
            if self.app_list_name and len(self.app_list_name) > 0:
                for app_name in self.app_list_name:
                    result = device.uninstall_package(app_name)
                    if result and (result.startswith("Success") or "successfully" in result):
                        LOG.debug("uninstalling package Success. result is %s" %
                                  result)
                    else:
                        LOG.warning("Error uninstalling package %s %s" %
                                    (device.__get_serial__(), result))
            else:
                for app in self.installed_app:
                    app_name = get_app_name(app)
                    if app_name:
                        result = device.uninstall_package(app_name)
                        if result and (result.startswith("Success") or "successfully" in result):
                            LOG.debug("uninstalling package Success. result is %s" %
                                      result)
                        else:
                            LOG.warning("Error uninstalling package %s %s" %
                                        (device.__get_serial__(), result))
                    else:
                        LOG.warning("Can't find app name for %s" % app)
        if self.is_pri_app:
            remount(device)
        for pushed_file in self.pushed_hap_file:
            device.execute_shell_command("rm -r %s" % pushed_file)

    def install_hap(self, device, hap_file):
        if self.is_pri_app:
            LOG.info("Install hap as privileged app {}".format(hap_file))
            hap_name = os.path.basename(hap_file).replace(".hap", "")
            try:
                with TemporaryDirectory(prefix=hap_name) as temp_dir:
                    zif_file = zipfile.ZipFile(hap_file)
                    zif_file.extractall(path=temp_dir)
                    entry_app = os.path.join(temp_dir, "Entry.app")
                    push_dest_dir = os.path.join("/system/priv-app/", hap_name)
                    device.execute_shell_command("rm -rf " + push_dest_dir,
                                                 output_flag=False)
                    device.push_file(entry_app, os.path.join(
                        push_dest_dir + os.path.basename(entry_app)))
                    device.push_file(hap_file, os.path.join(
                        push_dest_dir + os.path.basename(hap_file)))
                    self.pushed_hap_file.add(os.path.join(
                        push_dest_dir + os.path.basename(hap_file)))
                    device.reboot()
            except RuntimeError as exception:
                msg = "Install hap app failed withe error {}".format(exception)
                LOG.error(msg)
                raise Exception(msg)
            except Exception as exception:
                msg = "Install hap app failed withe exception {}".format(
                    exception)
                LOG.error(msg)
                raise Exception(msg)
            finally:
                zif_file.close()
        else:
            push_dest = "/%s" % "sdcard"
            push_dest = "%s/%s" % (push_dest, os.path.basename(hap_file))
            device.push_file(hap_file, push_dest)
            self.pushed_hap_file.add(push_dest)
            output = device.execute_shell_command("bm install -p " + push_dest)
            if not output.startswith("Success") and not "successfully" in output:
                output = output.strip()
                if "[ERROR_GET_BUNDLE_INSTALLER_FAILED]" not in output.upper():
                    raise AppInstallError(
                        "Failed to install %s on %s. Reason:%s" %
                        (push_dest, device.__get_serial__(), output))
                else:
                    LOG.info("'[ERROR_GET_BUNDLE_INSTALLER_FAILED]' occurs, "
                             "retry install hap")
                    exec_out = self.retry_install_hap(
                        device, "bm install -p " + push_dest)
                    if not exec_out.startswith("Success") and not "successfully" in output:
                        raise AppInstallError(
                            "Retry failed,Can't install %s on %s. Reason:%s" %
                            (push_dest, device.__get_serial__(), exec_out))
            else:
                LOG.debug("Install %s success" % push_dest)

    @classmethod
    def retry_install_hap(cls, device, command):
        if hasattr(device, "is_harmony") and device.is_harmony:
            real_command = ["hdc_std", "-t", str(device.device_sn), "-s",
                            "tcp:%s:%s" % (str(device.host), str(device.port)),
                            "shell", command]
        else:
            # hdc -t UID -s tcp:IP:PORT
            real_command = ["hdc", "-t", str(device.device_sn), "-s",
                            "tcp:%s:%s" % (str(device.host), str(device.port)),
                            "shell", command]
        message = "%s execute command: %s" % \
                  (convert_serial(device.device_sn), " ".join(real_command))
        LOG.info(message)
        exec_out = ""
        for wait_count in range(1, MAX_WAIT_COUNT):
            LOG.debug("Retry times:%s, wait %ss" %
                      (wait_count, (wait_count * 10)))
            time.sleep(wait_count * 10)
            exec_out = exec_cmd(real_command)
            if exec_out and exec_out.startswith("Success"):
                break
        if not exec_out:
            exec_out = "System is not in %s" % ["Windows", "Linux", "Darwin"]
        LOG.info("Retry install hap result is: [%s]" % exec_out.strip())
        return exec_out


@Plugin(type=Plugin.TEST_KIT, id=CKit.component)
class ComponentKit(ITestKit):

    def __init__(self):
        self._white_list_file = ""
        self._white_list = ""
        self._cap_file = ""
        self.paths = ""
        self.cache_subsystem = set()
        self.cache_part = set()

    def __check_config__(self, config):
        self._white_list_file =\
            get_config_value('white-list', config, is_list=False)
        self._cap_file = get_config_value('cap-file', config, is_list=False)
        self.paths = get_config_value('paths', config)

    def __setup__(self, device, **kwargs):
        if hasattr(device, ConfigConst.support_component):
            return
        if device.label in ["phone", "watch", "car", "tv", "tablet", "ivi"]:
            command = "cat %s" % self._cap_file
            result = device.execute_shell_command(command)
            part_set = set()
            subsystem_set = set()
            if "{" in result:
                for item in json.loads(result).get("components", []):
                    part_set.add(item.get("component", ""))
            subsystems, parts = self.get_white_list()
            part_set.update(parts)
            subsystem_set.update(subsystems)
            setattr(device, ConfigConst.support_component,
                    (subsystem_set, part_set))
            self.cache_subsystem.update(subsystem_set)
            self.cache_part.update(part_set)

    def get_cache(self):
        return self.cache_subsystem, self.cache_part

    def get_white_list(self):
        if not self._white_list and self._white_list_file:
            self._white_list = self._parse_white_list()
        return self._white_list

    def _parse_white_list(self):
        subsystem = set()
        part = set()
        white_json_file = os.path.normpath(self._white_list_file)
        if not os.path.isabs(white_json_file):
            white_json_file = \
                get_file_absolute_path(white_json_file, self.paths)
        if os.path.isfile(white_json_file):
            subsystem_list = list()
            flags = os.O_RDONLY
            modes = stat.S_IWUSR | stat.S_IRUSR
            with os.fdopen(os.open(white_json_file, flags, modes),
                           "r") as file_content:
                json_result = json.load(file_content)
                if "subsystems" in json_result.keys():
                    subsystem_list.extend(json_result["subsystems"])
                for subsystem_item_list in subsystem_list:
                    for key, value in subsystem_item_list.items():
                        if key == "subsystem":
                            subsystem.add(value)
                        elif key == "components":
                            for component_item in value:
                                if "component" in component_item.keys():
                                    part.add(
                                        component_item["component"])

        return subsystem, part

    def __teardown__(self, device):
        if hasattr(device, ConfigConst.support_component):
            setattr(device, ConfigConst.support_component, None)
        self._white_list_file = ""
        self._white_list = ""
        self._cap_file = ""
        self.cache_subsystem.clear()
        self.cache_part.clear()
        self.cache_device.clear()





def keep_screen_on(device):
    device.execute_shell_command("svc power stayon true")





def run_command(device, command):
    LOG.debug("The command:{} is running".format(command))
    stdout = None
    if command.strip() == "remount":
        remount(device)
    elif command.strip() == "reboot":
        device.reboot()
    elif command.strip() == "reboot-delay":
        pass
    else:
        stdout = device.execute_shell_command(command)
    LOG.debug("Run command result: %s" % (stdout if stdout else ""))
    return stdout


def junit_dex_para_parse(device, junit_paras, prefix_char="--"):
    """To parse the para of junit
    Args:
        device: the device running
        junit_paras: the para dict of junit
        prefix_char: the prefix char of parsed cmd
    Returns:
        the new para using in a command like -e testFile xxx
        -e coverage true...
    """
    ret_str = []
    path = "/%s/%s/%s" % ("data", "local", "ajur")
    include_file = "%s/%s" % (path, "includes.txt")
    exclude_file = "%s/%s" % (path, "excludes.txt")

    if not isinstance(junit_paras, dict):
        LOG.warning("The para of junit is not the dict format as required")
        return ""
    # Disable screen keyguard
    disable_key_guard = junit_paras.get('disable-keyguard')
    if not disable_key_guard or disable_key_guard[0].lower() != 'false':
        disable_keyguard(device)

    for para_name in junit_paras.keys():
        path = "/%s/%s/%s/" % ("data", "local", "ajur")
        if para_name.strip() == 'test-file-include-filter':
            for file_name in junit_paras[para_name]:
                device.push_file(file_name, include_file)
                device.execute_shell_command(
                    'chown -R shell:shell %s' % path)
            ret_str.append(prefix_char + " ".join(['testFile', include_file]))
        elif para_name.strip() == "test-file-exclude-filter":
            for file_name in junit_paras[para_name]:
                device.push_file(file_name, include_file)
                device.execute_shell_command(
                    'chown -R shell:shell %s' % path)
            ret_str.append(prefix_char + " ".join(['notTestFile',
                                                   exclude_file]))
        elif para_name.strip() == "test" or para_name.strip() == "class":
            result = get_class(junit_paras, prefix_char, para_name.strip())
            ret_str.append(result)
        elif para_name.strip() == "include-annotation":
            ret_str.append(prefix_char + " ".join(
                ['annotation', ",".join(junit_paras[para_name])]))
        elif para_name.strip() == "exclude-annotation":
            ret_str.append(prefix_char + " ".join(
                ['notAnnotation', ",".join(junit_paras[para_name])]))
        else:
            ret_str.append(prefix_char + " ".join(
                [para_name, ",".join(junit_paras[para_name])]))

    return " ".join(ret_str)


def get_app_name(hap_app):
    hap_name = os.path.basename(hap_app).replace(".hap", "")
    app_name = ""
    with TemporaryDirectory(prefix=hap_name) as temp_dir:
        zif_file = zipfile.ZipFile(hap_app)
        zif_file.extractall(path=temp_dir)
        config_json_file = ""
        name_list = ["module.json", "config.json"]
        for f_name in os.listdir(temp_dir):
            if f_name in name_list:
                config_json_file = os.path.join(temp_dir, f_name)
                break
        if not os.path.exists(config_json_file):
            LOG.debug("Neither config.json nor module.json in %s.hap"
                      % hap_name)
        else:
            flags = os.O_RDONLY
            modes = stat.S_IWUSR | stat.S_IRUSR
            with os.fdopen(os.open(config_json_file, flags, modes),
                           "r") as file_desc:
                attrs = json.loads(file_desc.read())
                if "app" in attrs.keys() and \
                        "bundleName" in attrs.get("app", dict()).keys():
                    app_name = attrs["app"]["bundleName"]
                    LOG.info("Obtain the app name {} from json "
                             "successfully".format(app_name))
                else:
                    LOG.debug("Tip: 'app' or 'bundleName' not "
                              "in %s.hap/config.json" % hap_name)
        zif_file.close()
    return app_name


def oh_jsunit_para_parse(runner, junit_paras):
    junit_paras = dict(junit_paras)
    test_type_list = ["function", "performance", "reliability", "security"]
    size_list = ["small", "medium", "large"]
    level_list = ["0", "1", "2", "3"]
    for para_name in junit_paras.keys():
        para_name = para_name.strip()
        para_values = junit_paras.get(para_name, [])
        if para_name == "class":
            runner.add_arg(para_name, ",".join(para_values))
        elif para_name == "notClass":
            runner.add_arg(para_name, ",".join(para_values))
        elif para_name == "testType":
            if para_values[0] not in test_type_list:
                continue
            # function/performance/reliability/security
            runner.add_arg(para_name, para_values[0])
        elif para_name == "size":
            if para_values[0] not in size_list:
                continue
            # size small/medium/large
            runner.add_arg(para_name, para_values[0])
        elif para_name == "level":
            if para_values[0] not in level_list:
                continue
            # 0/1/2/3/4
            runner.add_arg(para_name, para_values[0])
