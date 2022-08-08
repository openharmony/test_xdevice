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


class ParamError(Exception):
    def __init__(self, error_msg, error_no=""):
        super(ParamError, self).__init__(error_msg, error_no)
        self.error_msg = error_msg
        self.error_no = error_no

    def __str__(self):
        return str(self.error_msg)


class DeviceError(Exception):
    def __init__(self, error_msg, error_no=""):
        super(DeviceError, self).__init__(error_msg, error_no)
        self.error_msg = error_msg
        self.error_no = error_no

    def __str__(self):
        return str(self.error_msg)


class ExecuteTerminate(Exception):
    def __init__(self, error_msg="ExecuteTerminate", error_no=""):
        super(ExecuteTerminate, self).__init__(error_msg, error_no)
        self.error_msg = error_msg
        self.error_no = error_no

    def __str__(self):
        return str(self.error_msg)


class ReportException(Exception):
    """
    Exception thrown when a shell command executed on a device takes too long
    to send its output.
    """
    def __init__(self, error_msg="ReportException", error_no=""):
        super(ReportException, self).__init__(error_msg, error_no)
        self.error_msg = error_msg
        self.error_no = error_no

    def __str__(self):
        return str(self.error_msg)


class LiteDeviceError(Exception):
    def __init__(self, error_msg, error_no=""):
        super(LiteDeviceError, self).__init__(error_msg, error_no)
        self.error_msg = error_msg
        self.error_no = error_no

    def __str__(self):
        return str(self.error_msg)


class HdcError(DeviceError):
    """
    Raised when there is an error in hdc operations.
    """

    def __init__(self, error_msg, error_no=""):
        super(HdcError, self).__init__(error_msg, error_no)
        self.error_msg = error_msg
        self.error_no = error_no

    def __str__(self):
        return str(self.error_msg)


class HdcCommandRejectedException(HdcError):
    """
    Exception thrown when hdc refuses a command.
    """

    def __init__(self, error_msg, error_no=""):
        super(HdcCommandRejectedException, self).__init__(error_msg, error_no)
        self.error_msg = error_msg
        self.error_no = error_no

    def __str__(self):
        return str(self.error_msg)


class ShellCommandUnresponsiveException(HdcError):
    """
    Exception thrown when a shell command executed on a device takes too long
    to send its output.
    """
    def __init__(self, error_msg="ShellCommandUnresponsiveException",
                 error_no=""):
        super(ShellCommandUnresponsiveException, self).\
            __init__(error_msg, error_no)
        self.error_msg = error_msg
        self.error_no = error_no

    def __str__(self):
        return str(self.error_msg)


class DeviceUnresponsiveException(HdcError):
    """
    Exception thrown when a shell command executed on a device takes too long
    to send its output.
    """
    def __init__(self, error_msg="DeviceUnresponsiveException", error_no=""):
        super(DeviceUnresponsiveException, self).__init__(error_msg, error_no)
        self.error_msg = error_msg
        self.error_no = error_no

    def __str__(self):
        return str(self.error_msg)


class AppInstallError(DeviceError):
    def __init__(self, error_msg, error_no=""):
        super(AppInstallError, self).__init__(error_msg, error_no)
        self.error_msg = error_msg
        self.error_no = error_no

    def __str__(self):
        return str(self.error_msg)


class HapNotSupportTest(DeviceError):
    def __init__(self, error_msg, error_no=""):
        super(HapNotSupportTest, self).__init__(error_msg, error_no)
        self.error_msg = error_msg
        self.error_no = error_no

    def __str__(self):
        return str(self.error_msg)