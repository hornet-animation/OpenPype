#!/usr/bin/env python
#
# Copyright 2018 Pixar Animation Studios
#
# Licensed under the Apache License, Version 2.0 (the "Apache License")
# with the following modification; you may not use this file except in
# compliance with the Apache License and the following modification to it:
# Section 6. Trademarks. is deleted and replaced with:
#
# 6. Trademarks. This License does not grant permission to use the trade
#    names, trademarks, service marks, or product names of the Licensor
#    and its affiliates, except as required to comply with Section 4(c) of
#    the License and to reproduce the content of the NOTICE file.
#
# You may obtain a copy of the Apache License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the Apache License with the above modification is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the Apache License for the specific
# language governing permissions and limitations under the Apache License.
#

"""Utility assertions for OTIO Unit tests."""

import re

from . import (
    adapters
)


class OTIOAssertions(object):
    def assertJsonEqual(self, known, test_result):
        """Convert to json and compare that (more readable)."""
        self.maxDiff = None

        known_str = adapters.write_to_string(known, 'otio_json')
        test_str = adapters.write_to_string(test_result, 'otio_json')

        def strip_trailing_decimal_zero(s):
            return re.sub(r'"(value|rate)": (\d+)\.0', r'"\1": \2', s)

        self.assertMultiLineEqual(
            strip_trailing_decimal_zero(known_str),
            strip_trailing_decimal_zero(test_str)
        )

    def assertIsOTIOEquivalentTo(self, known, test_result):
        """Test using the 'is equivalent to' method on SerializableObject"""

        self.assertTrue(known.is_equivalent_to(test_result))
