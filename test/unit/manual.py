"""
Unit testing for the stem.manual module.
"""

import io
import os
import re
import sqlite3
import tempfile
import unittest

import stem.prereq
import stem.manual
import stem.util.system
import test.require

try:
  # account for urllib's change between python 2.x and 3.x
  import urllib.request as urllib
except ImportError:
  import urllib2 as urllib

try:
  # added in python 3.3
  from unittest.mock import Mock, patch
except ImportError:
  from mock import Mock, patch

try:
  # added in python 2.7
  from collections import OrderedDict
except ImportError:
  from stem.util.ordereddict import OrderedDict

URL_OPEN = 'urllib.request.urlopen' if stem.prereq.is_python_3() else 'urllib2.urlopen'
EXAMPLE_MAN_PATH = os.path.join(os.path.dirname(__file__), 'tor_man_example')
UNKNOWN_OPTIONS_MAN_PATH = os.path.join(os.path.dirname(__file__), 'tor_man_with_unknown')

EXPECTED_DESCRIPTION = 'Tor is a connection-oriented anonymizing communication service. Users choose a source-routed path through a set of nodes, and negotiate a "virtual circuit" through the network, in which each node knows its predecessor and successor, but no others. Traffic flowing down the circuit is unwrapped by a symmetric key at each node, which reveals the downstream node.'

EXPECTED_CLI_OPTIONS = {
  '-f FILE': 'Specify a new configuration file to contain further Tor configuration options OR pass - to make Tor read its configuration from standard input. (Default: @CONFDIR@/torrc, or $HOME/.torrc if that file is not found)',
  '-h, -help': 'Display a short help message and exit.',
  '--allow-missing-torrc': 'Do not require that configuration file specified by -f exist if default torrc can be accessed.',
}

EXPECTED_SIGNALS = {
  'SIGHUP': 'The signal instructs Tor to reload its configuration (including closing and reopening logs), and kill and restart its helper processes if applicable.',
  'SIGTERM': 'Tor will catch this, clean up and sync to disk if necessary, and exit.',
  'SIGINT': 'Tor clients behave as with SIGTERM; but Tor servers will do a controlled slow shutdown, closing listeners and waiting 30 seconds before exiting. (The delay can be configured with the ShutdownWaitLength config option.)',
}

EXPECTED_FILES = {
  '@LOCALSTATEDIR@/lib/tor/': 'The tor process stores keys and other data here.',
  'DataDirectory/cached-status/': 'The most recently downloaded network status document for each authority. Each file holds one such document; the filenames are the hexadecimal identity key fingerprints of the directory authorities. Mostly obsolete.',
  'DataDirectory/cached-certs': 'This file holds downloaded directory key certificates that are used to verify authenticity of documents generated by Tor directory authorities.',
  'DataDirectory/state': 'A set of persistent key-value mappings. These are documented in the file. These include: o   The current entry guards and their status. o   The current bandwidth accounting values (unused so far; see below). o   When the file was last written o   What version of Tor generated the state file o   A short history of bandwidth usage, as produced in the server descriptors.',
  '@CONFDIR@/torrc': 'The configuration file, which contains "option value" pairs.',
  'DataDirectory/bw_accounting': "Used to track bandwidth accounting values (when the current period starts and ends; how much has been read and written so far this period). This file is obsolete, and the data is now stored in the 'state' file as well. Only used when bandwidth accounting is enabled.",
  '$HOME/.torrc': 'Fallback location for torrc, if @CONFDIR@/torrc is not found.',
}

EXPECTED_CONFIG_OPTIONS = OrderedDict()

EXPECTED_CONFIG_OPTIONS['BandwidthRate'] = stem.manual.ConfigOption(
  name = 'BandwidthRate',
  category = 'General',
  usage = 'N bytes|KBytes|MBytes|GBytes|KBits|MBits|GBits',
  summary = 'Average bandwidth usage limit',
  description = 'A token bucket limits the average incoming bandwidth usage on this node to the specified number of bytes per second, and the average outgoing bandwidth usage to that same value. If you want to run a relay in the public network, this needs to be at the very least 75 KBytes for a relay (that is, 600 kbits) or 50 KBytes for a bridge (400 kbits) -- but of course, more is better; we recommend at least 250 KBytes (2 mbits) if possible. (Default: 1 GByte)\n\nWith this option, and in other options that take arguments in bytes, KBytes, and so on, other formats are also supported. Notably, "KBytes" can also be written as "kilobytes" or "kb"; "MBytes" can be written as "megabytes" or "MB"; "kbits" can be written as "kilobits"; and so forth. Tor also accepts "byte" and "bit" in the singular. The prefixes "tera" and "T" are also recognized. If no units are given, we default to bytes. To avoid confusion, we recommend writing "bytes" or "bits" explicitly, since it\'s easy to forget that "B" means bytes, not bits.')

EXPECTED_CONFIG_OPTIONS['BandwidthBurst'] = stem.manual.ConfigOption(
  name = 'BandwidthBurst',
  category = 'General',
  usage = 'N bytes|KBytes|MBytes|GBytes|KBits|MBits|GBits',
  summary = 'Maximum bandwidth usage limit',
  description = 'Limit the maximum token bucket size (also known as the burst) to the given number of bytes in each direction. (Default: 1 GByte)')

EXPECTED_CONFIG_OPTIONS['MaxAdvertisedBandwidth'] = stem.manual.ConfigOption(
  name = 'MaxAdvertisedBandwidth',
  category = 'General',
  usage = 'N bytes|KBytes|MBytes|GBytes|KBits|MBits|GBits',
  summary = 'Limit for the bandwidth we advertise as being available for relaying',
  description = 'If set, we will not advertise more than this amount of bandwidth for our BandwidthRate. Server operators who want to reduce the number of clients who ask to build circuits through them (since this is proportional to advertised bandwidth rate) can thus reduce the CPU demands on their server without impacting network performance.')

EXPECTED_CONFIG_OPTIONS['Bridge'] = stem.manual.ConfigOption(
  name = 'Bridge',
  category = 'Client',
  usage = '[transport] IP:ORPort [fingerprint]',
  summary = 'Available bridges',
  description = 'When set along with UseBridges, instructs Tor to use the relay at "IP:ORPort" as a "bridge" relaying into the Tor network. If "fingerprint" is provided (using the same format as for DirAuthority), we will verify that the relay running at that location has the right fingerprint. We also use fingerprint to look up the bridge descriptor at the bridge authority, if it\'s provided and if UpdateBridgesFromAuthority is set too.\n\nIf "transport" is provided, and matches to a ClientTransportPlugin line, we use that pluggable transports proxy to transfer data to the bridge.')

CACHED_MANUAL = None


def _cached_manual():
  global CACHED_MANUAL

  if CACHED_MANUAL is None:
    CACHED_MANUAL = stem.manual.Manual.from_cache()

  return CACHED_MANUAL


class TestManual(unittest.TestCase):
  def test_query(self):
    self.assertEqual("If set, this option overrides the default location and file name for Tor's cookie file. (See CookieAuthentication above.)", stem.manual.query('SELECT description FROM torrc WHERE name="CookieAuthFile"').fetchone()[0])

  def test_query_on_failure(self):
    self.assertRaisesRegexp(sqlite3.OperationalError, 'near "hello": syntax error', stem.manual.query, 'hello world')

  def test_query_with_missing_database(self):
    self.assertRaisesRegexp(IOError, "/no/such/path doesn't exist", stem.manual.query, 'SELECT * FROM torrc', '/no/such/path')

  def test_has_all_summaries(self):
    """
    Check that we have brief, human readable summaries for all of tor's
    configuration options. If you add a new config entry then please take a sec
    to write a little summary. They're located in 'stem/settings.cfg'.
    """

    manual = _cached_manual()
    present = set(manual.config_options.keys())
    expected = set([key[15:] for key in stem.manual._config(lowercase = False) if key.startswith('manual.summary.')])

    missing_options = present.difference(expected)
    extra_options = expected.difference(present)

    if missing_options:
      self.fail("Ran cache_manual.py? Please update Stem's settings.cfg with summaries of the following config options: %s" % ', '.join(missing_options))
    elif extra_options:
      self.fail("Ran cache_manual.py? Please remove the following summaries from Stem's settings.cfg: %s" % ', '.join(extra_options))

  def test_is_important(self):
    self.assertTrue(stem.manual.is_important('ExitPolicy'))
    self.assertTrue(stem.manual.is_important('exitpolicy'))
    self.assertTrue(stem.manual.is_important('EXITPOLICY'))

    self.assertFalse(stem.manual.is_important('ConstrainedSockSize'))

  def test_minimal_config_option(self):
    blank = stem.manual.ConfigOption('UnknownOption')

    self.assertEqual(stem.manual.Category.UNKNOWN, blank.category)
    self.assertEqual('UnknownOption', blank.name)
    self.assertEqual('', blank.usage)
    self.assertEqual('', blank.summary)
    self.assertEqual('', blank.description)

  @test.require.command('man')
  def test_parsing_with_example(self):
    """
    Read a trimmed copy of tor's man page. This gives a good exercise of our
    parser with static content. As new oddball man oddities appear feel free to
    expand our example (or add another).
    """

    if stem.util.system.is_mac():
      self.skipTest('(man lacks --encoding arg on OSX, #18660)')
      return

    manual = stem.manual.Manual.from_man(EXAMPLE_MAN_PATH)

    self.assertEqual('tor - The second-generation onion router', manual.name)
    self.assertEqual('tor [OPTION value]...', manual.synopsis)
    self.assertEqual(EXPECTED_DESCRIPTION, manual.description)
    self.assertEqual(EXPECTED_CLI_OPTIONS, manual.commandline_options)
    self.assertEqual(EXPECTED_SIGNALS, manual.signals)
    self.assertEqual(EXPECTED_FILES, manual.files)
    self.assertEqual(EXPECTED_CONFIG_OPTIONS, manual.config_options)

  @test.require.command('man')
  def test_parsing_with_unknown_options(self):
    """
    Check that we can read a local mock man page that contains unrecognized
    options. Unlike most other tests this doesn't require network access.
    """

    if stem.util.system.is_mac():
      self.skipTest('(man lacks --encoding arg on OSX, #18660)')
      return

    manual = stem.manual.Manual.from_man(UNKNOWN_OPTIONS_MAN_PATH)

    self.assertEqual('tor - The second-generation onion router', manual.name)
    self.assertEqual('', manual.synopsis)
    self.assertEqual('', manual.description)
    self.assertEqual({}, manual.commandline_options)
    self.assertEqual({}, manual.signals)
    self.assertEqual({}, manual.files)

    self.assertEqual(2, len(manual.config_options))

    option = [entry for entry in manual.config_options.values() if entry.category == stem.manual.Category.UNKNOWN][0]
    self.assertEqual(stem.manual.Category.UNKNOWN, option.category)
    self.assertEqual('SpiffyNewOption', option.name)
    self.assertEqual('transport exec path-to-binary [options]', option.usage)
    self.assertEqual('', option.summary)
    self.assertEqual('Description of this new option.', option.description)

  @test.require.command('man')
  def test_saving_manual_as_config(self):
    """
    Check that we can save and reload manuals as a config.
    """

    manual = stem.manual.Manual.from_man(EXAMPLE_MAN_PATH)

    with tempfile.NamedTemporaryFile(prefix = 'saved_test_manual.') as tmp:
      manual.save(tmp.name)
      loaded_manual = stem.manual.Manual.from_cache(tmp.name)
      self.assertEqual(manual, loaded_manual)

  def test_saving_manual_as_sqlite(self):
    """
    Check that we can save and reload manuals as sqlite.
    """

    manual = stem.manual.Manual.from_man(EXAMPLE_MAN_PATH)

    with tempfile.NamedTemporaryFile(prefix = 'saved_test_manual.', suffix = '.sqlite') as tmp:
      manual.save(tmp.name)
      loaded_manual = stem.manual.Manual.from_cache(tmp.name)
      self.assertEqual(manual, loaded_manual)

  def test_cached_manual(self):
    manual = _cached_manual()

    self.assertEqual('tor - The second-generation onion router', manual.name)
    self.assertEqual('tor [OPTION value]...', manual.synopsis)
    self.assertTrue(manual.description.startswith(EXPECTED_DESCRIPTION))
    self.assertTrue(len(manual.commandline_options) > 10)
    self.assertTrue(len(manual.signals) > 5)
    self.assertTrue(len(manual.files) > 20)
    self.assertTrue(len(manual.config_options) > 200)

  def test_download_man_page_without_arguments(self):
    exc_msg = "Either the path or file_handle we're saving to must be provided"
    self.assertRaisesRegexp(ValueError, exc_msg, stem.manual.download_man_page)

  @patch('stem.util.system.is_available', Mock(return_value = False))
  def test_download_man_page_requires_a2x(self):
    exc_msg = 'We require a2x from asciidoc to provide a man page'
    self.assertRaisesRegexp(IOError, exc_msg, stem.manual.download_man_page, '/tmp/no_such_file')

  @patch('tempfile.mkdtemp', Mock(return_value = '/no/such/path'))
  @patch('shutil.rmtree', Mock())
  @patch('stem.manual.open', Mock(side_effect = IOError('unable to write to file')), create = True)
  @patch('stem.util.system.is_available', Mock(return_value = True))
  def test_download_man_page_when_unable_to_write(self):
    exc_msg = "Unable to download tor's manual from https://gitweb.torproject.org/tor.git/plain/doc/tor.1.txt to /no/such/path/tor.1.txt: unable to write to file"
    self.assertRaisesRegexp(IOError, re.escape(exc_msg), stem.manual.download_man_page, '/tmp/no_such_file')

  @patch('tempfile.mkdtemp', Mock(return_value = '/no/such/path'))
  @patch('shutil.rmtree', Mock())
  @patch('stem.manual.open', Mock(return_value = io.BytesIO()), create = True)
  @patch('stem.util.system.is_available', Mock(return_value = True))
  @patch(URL_OPEN, Mock(side_effect = urllib.URLError('<urlopen error [Errno -2] Name or service not known>')))
  def test_download_man_page_when_download_fails(self):
    exc_msg = "Unable to download tor's manual from https://www.atagar.com/foo/bar to /no/such/path/tor.1.txt: <urlopen error <urlopen error [Errno -2] Name or service not known>>"
    self.assertRaisesRegexp(IOError, re.escape(exc_msg), stem.manual.download_man_page, '/tmp/no_such_file', url = 'https://www.atagar.com/foo/bar')

  @patch('tempfile.mkdtemp', Mock(return_value = '/no/such/path'))
  @patch('shutil.rmtree', Mock())
  @patch('stem.manual.open', Mock(return_value = io.BytesIO()), create = True)
  @patch('stem.util.system.call', Mock(side_effect = stem.util.system.CallError('call failed', 'a2x -f manpage /no/such/path/tor.1.txt', 1, None, None, 'call failed')))
  @patch('stem.util.system.is_available', Mock(return_value = True))
  @patch(URL_OPEN, Mock(return_value = io.BytesIO(b'test content')))
  def test_download_man_page_when_a2x_fails(self):
    exc_msg = "Unable to run 'a2x -f manpage /no/such/path/tor.1.txt': call failed"
    self.assertRaisesRegexp(IOError, exc_msg, stem.manual.download_man_page, '/tmp/no_such_file', url = 'https://www.atagar.com/foo/bar')

  @patch('tempfile.mkdtemp', Mock(return_value = '/no/such/path'))
  @patch('shutil.rmtree', Mock())
  @patch('stem.manual.open', create = True)
  @patch('stem.util.system.call')
  @patch('stem.util.system.is_available', Mock(return_value = True))
  @patch('os.path.exists', Mock(return_value = True))
  @patch(URL_OPEN, Mock(return_value = io.BytesIO(b'test content')))
  def test_download_man_page_when_successful(self, call_mock, open_mock):
    open_mock.side_effect = lambda path, *args: {
      '/no/such/path/tor.1.txt': io.BytesIO(),
      '/no/such/path/tor.1': io.BytesIO(b'a2x output'),
    }[path]

    call_mock.return_value = Mock()

    output = io.BytesIO()
    stem.manual.download_man_page(file_handle = output)
    self.assertEqual(b'a2x output', output.getvalue())
    call_mock.assert_called_once_with('a2x -f manpage /no/such/path/tor.1.txt')

  @patch('stem.util.system.is_mac', Mock(return_value = False))
  @patch('stem.util.system.call', Mock(side_effect = OSError('man --encoding=ascii -P cat tor returned exit status 16')))
  def test_from_man_when_manual_is_unavailable(self):
    exc_msg = "Unable to run 'man --encoding=ascii -P cat tor': man --encoding=ascii -P cat tor returned exit status 16"
    self.assertRaisesRegexp(IOError, exc_msg, stem.manual.Manual.from_man)

  @patch('stem.util.system.call', Mock(return_value = []))
  def test_when_man_is_empty(self):
    manual = stem.manual.Manual.from_man()

    self.assertEqual('', manual.name)
    self.assertEqual('', manual.synopsis)
    self.assertEqual('', manual.description)
    self.assertEqual({}, manual.commandline_options)
    self.assertEqual({}, manual.signals)
    self.assertEqual({}, manual.files)
    self.assertEqual(OrderedDict(), manual.config_options)
