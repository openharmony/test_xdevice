#!/usr/bin/env python3
# coding=utf-8

#
# Copyright (c) 2020-2022 Huawei Device Co., Ltd.
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

from dataclasses import dataclass


__all__ = ["ComType", "HostDrivenTestType",
           "ParserType", "DeviceLiteKernel", "CKit"]


@dataclass
class ComType(object):
    """
    ComType enumeration
    """
    cmd_com = "cmd"
    deploy_com = "deploy"


@dataclass
class HostDrivenTestType(object):
    """
    HostDrivenType enumeration
    """
    device_test = "DeviceTest"
    windows_test = "WindowsTest"


@dataclass
class ParserType:
    ctest_lite = "CTestLite"
    cpp_test_lite = "CppTestLite"
    cpp_test_list_lite = "CppTestListLite"
    open_source_test = "OpenSourceTest"
    build_only_test = "BuildOnlyTestLite"
    jsuit_test_lite = "JSUnitTestLite"


@dataclass
class DeviceLiteKernel(object):
    """
    Lite device os enumeration
    """
    linux_kernel = "linux"
    lite_kernel = "lite"


@dataclass
class CKit:
    push = "PushKit"
    install = "ApkInstallKit"
    liteinstall = "LiteAppInstallKit"
    command = "CommandKit"
    config = "ConfigKit"
    wifi = "WIFIKit"
    propertycheck = 'PropertyCheckKit'
    sts = 'STSKit'
    shell = "ShellKit"
    deploy = 'DeployKit'
    mount = 'MountKit'
    liteuikit = 'LiteUiKit'
    rootfs = "RootFsKit"
    liteshell = "LiteShellKit"
    app_install = "AppInstallKit"
    deploytool = "DeployToolKit"
    query = "QueryKit"
    component = "ComponentKit"
