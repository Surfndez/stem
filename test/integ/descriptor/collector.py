"""
Integration tests for stem.descriptor.collector.
"""

import datetime
import re
import unittest

import test.require

import stem.descriptor.collector

from stem.descriptor import Compression

RECENT = datetime.datetime.utcnow() - datetime.timedelta(minutes = 60)


class TestCollector(unittest.TestCase):
  @test.require.only_run_once
  @test.require.online
  def test_index_plaintext(self):
    self._test_index(None)

  @test.require.only_run_once
  @test.require.online
  def test_index_gzip(self):
    self._test_index(Compression.GZIP)

  @test.require.only_run_once
  @test.require.online
  def test_index_bz2(self):
    self._test_index(Compression.BZ2)

  @test.require.only_run_once
  @test.require.online
  def test_index_lzma(self):
    self._test_index(Compression.LZMA)

  @test.require.only_run_once
  @test.require.online
  def test_downloading_server_descriptors(self):
    recent_descriptors = list(stem.descriptor.collector.get_server_descriptors(start = RECENT))

    if not (300 < len(recent_descriptors) < 800):
      self.fail('Downloaded %i descriptors, expected 300-800' % len(recent_descriptors))  # 584 on 8/5/19

  @test.require.only_run_once
  @test.require.online
  def test_downloading_extrainfo_descriptors(self):
    recent_descriptors = list(stem.descriptor.collector.get_extrainfo_descriptors(start = RECENT))

    if not (300 < len(recent_descriptors) < 800):
      self.fail('Downloaded %i descriptors, expected 300-800' % len(recent_descriptors))  # 583 on 8/7/19

  @test.require.only_run_once
  @test.require.online
  def test_downloading_microdescriptors(self):
    recent_descriptors = list(stem.descriptor.collector.get_microdescriptors(start = RECENT))

    if not (10 < len(recent_descriptors) < 100):
      self.fail('Downloaded %i descriptors, expected 10-100' % len(recent_descriptors))  # 23 on 8/7/19

  @test.require.only_run_once
  @test.require.online
  def test_downloading_consensus_v3(self):
    recent_descriptors = list(stem.descriptor.collector.get_consensus(start = RECENT))

    if not (3000 < len(recent_descriptors) < 10000):
      self.fail('Downloaded %i descriptors, expected 3000-10000' % len(recent_descriptors))  # 6554 on 8/10/19

  @test.require.only_run_once
  @test.require.online
  def test_downloading_consensus_micro(self):
    recent_descriptors = list(stem.descriptor.collector.get_consensus(start = RECENT, microdescriptor = True))

    if not (3000 < len(recent_descriptors) < 10000):
      self.fail('Downloaded %i descriptors, expected 3000-10000' % len(recent_descriptors))

  def test_downloading_consensus_invalid_type(self):
    test_values = (
      ({'version': 2, 'microdescriptor': True}, 'Only v3 microdescriptors are available (not version 2)'),
      ({'version': 1}, 'Only v2 and v3 router status entries are available (not version 1)'),
      ({'version': 4}, 'Only v2 and v3 router status entries are available (not version 4)'),
    )

    for args, expected_msg in test_values:
      self.assertRaisesRegexp(ValueError, re.escape(expected_msg), list, stem.descriptor.collector.get_consensus(**args))

  def _test_index(self, compression):
    if compression and not compression.available:
      self.skipTest('(%s unavailable)' % compression)
      return

    collector = stem.descriptor.collector.CollecTor()
    index = collector.index(compression = compression)

    self.assertEqual('https://collector.torproject.org', index['path'])
    self.assertEqual(['archive', 'contrib', 'recent'], [entry['path'] for entry in index['directories']])
