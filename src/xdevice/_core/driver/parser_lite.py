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

from queue import Queue
from _core.interface import IParser
from _core.report.encrypt import check_pub_key_exist
from _core.logger import platform_logger

__all__ = ["ShellHandler"]

LOG = platform_logger("ParserLite")


class ShellHandler:
    def __init__(self, parsers):
        self.parsers = []
        self.unfinished_line = ""
        self.output_queue = Queue()
        for parser in parsers:
            if isinstance(parser, IParser):
                self.parsers.append(parser)
            else:
                raise TypeError(
                    "Parser {} must implement IOutputParser interface.".format(
                        parser, ))

    def _process_output(self, output, end_mark="\n"):
        content = output
        if self.unfinished_line:
            content = "".join((self.unfinished_line, content))
            self.unfinished_line = ""
        lines = content.split(end_mark)
        if content.endswith(end_mark):
            # get rid of the tail element of this list contains empty str
            return lines[:-1]
        else:
            self.unfinished_line = lines[-1]
            # not return the tail element of this list contains unfinished str,
            # so we set position -1
            return lines

    def __read__(self, output):
        lines = self._process_output(output)
        for line in lines:
            for parser in self.parsers:
                try:
                    parser.__process__([line])
                except (ValueError, TypeError, SyntaxError, AttributeError) \
                        as error:
                    LOG.debug("Parse %s line error: %s" % (line, error))

    def __error__(self, message):
        if message:
            for parser in self.parsers:
                parser.__process__([message])

    def __done__(self, result_code="", message=""):
        msg_fmt = ""
        if message:
            msg_fmt = ", message is {}".format(message)
            for parser in self.parsers:
                parser.__process__([message])
        if not check_pub_key_exist():
            LOG.debug("Result code is: {}{}".format(result_code, msg_fmt))
        for parser in self.parsers:
            parser.__done__()
