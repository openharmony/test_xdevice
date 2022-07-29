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

from setuptools import setup

INSTALL_REQUIRES = []


def main():
    setup(name='xdevice-ohos',
          description='plugin for ohos',
          url='',
          package_dir={'': 'src'},
          packages=['ohos',
                    'ohos.drivers',
                    'ohos.environment',
                    'ohos.executor',
                    'ohos.managers',
                    'ohos.parser',
                    'ohos.testkit'
                    ],
          entry_points={
              'device': [
                  'device=ohos.environment.device',
                  'device_lite=ohos.environment.device_lite'
              ],
              'manager': [
                  'manager=ohos.managers.manager_device',
                  'manager_lite=ohos.managers.manager_lite'
              ],
              'driver': [
                  'drivers=ohos.drivers.drivers',
                  'drivers_lite=ohos.drivers.drivers_lite',
                  'homevision=ohos.drivers.homevision',
                  'kunpeng=ohos.drivers.kunpeng',
                  'openharmony=ohos.drivers.openharmony'
              ],
              'listener': [
                  'listener=ohos.executor.listener',
              ],
              'testkit': [
                  'kit=ohos.testkit.kit',
                  'kit_lite=ohos.testkit.kit_lite'
              ],
              'parser': [
                  'parser_lite=ohos.parser.parser_lite',
                  'parser=ohos.parser.parser'

              ]
          },
          zip_safe=False,
          install_requires=INSTALL_REQUIRES,
          )


if __name__ == "__main__":
    main()
