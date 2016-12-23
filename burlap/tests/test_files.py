import hashlib
import unittest

from mock import patch
import pytest


@patch('burlap.require.files._mode')
@patch('burlap.require.files._owner')
@patch('burlap.require.files.umask')
@patch('burlap.require.files.put')
@patch('burlap.require.files.md5sum')
@patch('burlap.require.files.is_file')
class FilesTestCase(unittest.TestCase):

    def _file(self, *args, **kwargs):
        """ Proxy to ensure ImportErrors actually cause test failures rather
        than trashing the test run entirely """
        from burlap import require
        require.files.file(*args, **kwargs)

    def test_verify_remote_false(self, is_file, md5sum, put, umask, owner, mode):
        """ If verify_remote is set to False, then we should find that
        only is_file is used to check for the file's existence. Hashlib's
        md5 should not have been called.
        """
        is_file.return_value = True
        self._file(contents='This is a test', verify_remote=False)
        self.assertTrue(is_file.called)
        self.assertFalse(md5sum.called)

    def test_verify_remote_true(self, is_file, md5sum, put, umask, owner, mode):
        """ If verify_remote is True, then we should find that an MD5 hash is
        used to work out whether the file is different.
        """
        is_file.return_value = True
        md5sum.return_value = hashlib.md5('This is a test').hexdigest()
        self._file(contents='This is a test', verify_remote=True)
        self.assertTrue(is_file.called)
        self.assertTrue(md5sum.called)

    def test_temp_dir(self, is_file, md5sum, put, umask, owner, mode):
        owner.return_value = 'root'
        umask.return_value = '0002'
        mode.return_value = '0664'
        from burlap import require
        require.file('/var/tmp/foo', source=__file__, use_sudo=True, temp_dir='/somewhere')
        put.assert_called_with(__file__, '/var/tmp/foo', use_sudo=True, temp_dir='/somewhere')

    def test_home_as_temp_dir(self, is_file, md5sum, put, umask, owner, mode):
        owner.return_value = 'root'
        umask.return_value = '0002'
        mode.return_value = '0664'
        from burlap import require
        require.file('/var/tmp/foo', source=__file__, use_sudo=True, temp_dir='')
        put.assert_called_with(__file__, '/var/tmp/foo', use_sudo=True, temp_dir='')

    def test_default_temp_dir(self, is_file, md5sum, put, umask, owner, mode):
        owner.return_value = 'root'
        umask.return_value = '0002'
        mode.return_value = '0664'
        from burlap import require
        require.file('/var/tmp/foo', source=__file__, use_sudo=True)
        put.assert_called_with(__file__, '/var/tmp/foo', use_sudo=True, temp_dir='/tmp')


class TestUploadTemplate(unittest.TestCase):

    @patch('burlap.files.run')
    @patch('burlap.files._upload_template')
    def test_mkdir(self, mock_upload_template, mock_run):

        from burlap.files import upload_template

        upload_template('filename', '/path/to/destination', mkdir=True)

        args, kwargs = mock_run.call_args
        self.assertEqual(args[0], 'mkdir -p /path/to')

    @patch('burlap.files.sudo')
    @patch('burlap.files._upload_template')
    def test_mkdir_sudo(self, mock_upload_template, mock_sudo):

        from burlap.files import upload_template

        upload_template('filename', '/path/to/destination', mkdir=True, use_sudo=True)

        args, kwargs = mock_sudo.call_args
        self.assertEqual(args[0], 'mkdir -p /path/to')
        self.assertEqual(kwargs['user'], None)

    @patch('burlap.files.sudo')
    @patch('burlap.files._upload_template')
    def test_mkdir_sudo_user(self, mock_upload_template, mock_sudo):

        from burlap.files import upload_template

        upload_template('filename', '/path/to/destination', mkdir=True, use_sudo=True, user='alice')

        args, kwargs = mock_sudo.call_args
        self.assertEqual(args[0], 'mkdir -p /path/to')
        self.assertEqual(kwargs['user'], 'alice')

    @patch('burlap.files.run_as_root')
    @patch('burlap.files._upload_template')
    def test_chown(self, mock_upload_template, mock_run_as_root):

        from fabric.api import env
        from burlap.files import upload_template

        upload_template('filename', 'destination', chown=True)

        args, kwargs = mock_run_as_root.call_args
        self.assertEqual(args[0], 'chown %s: destination' % env.user)

    @patch('burlap.files.run_as_root')
    @patch('burlap.files._upload_template')
    def test_chown_user(self, mock_upload_template, mock_run_as_root):

        from burlap.files import upload_template

        upload_template('filename', 'destination', chown=True, user='alice')

        args, kwargs = mock_run_as_root.call_args
        self.assertEqual(args[0], 'chown alice: destination')

    @patch('burlap.files._upload_template')
    def test_use_jinja_true(self, mock_upload_template):

        from burlap.files import upload_template

        upload_template('filename', 'destination', use_jinja=True)

        args, kwargs = mock_upload_template.call_args
        self.assertEqual(kwargs['use_jinja'], True)

    @patch('burlap.files._upload_template')
    def test_use_jinja_false(self, mock_upload_template):

        from burlap.files import upload_template

        upload_template('filename', 'destination', use_jinja=False)

        args, kwargs = mock_upload_template.call_args
        self.assertEqual(kwargs['use_jinja'], False)


@pytest.yield_fixture(scope='module')
def mock_run():
    with patch('burlap.files.run') as mock:
        yield mock


def test_copy(mock_run):
    from burlap.files import copy
    copy('/tmp/src', '/tmp/dst')
    mock_run.assert_called_with('/bin/cp /tmp/src /tmp/dst')


def test_copy_recursive(mock_run):
    from burlap.files import copy
    copy('/tmp/src', '/tmp/dst', recursive=True)
    mock_run.assert_called_with('/bin/cp -r /tmp/src /tmp/dst')


def test_move(mock_run):
    from burlap.files import move
    move('/tmp/src', '/tmp/dst')
    mock_run.assert_called_with('/bin/mv /tmp/src /tmp/dst')


def test_symlink(mock_run):
    from burlap.files import symlink
    symlink('/tmp/src', '/tmp/dst')
    mock_run.assert_called_with('/bin/ln -s /tmp/src /tmp/dst')


def test_remove(mock_run):
    from burlap.files import remove
    remove('/tmp/src')
    mock_run.assert_called_with('/bin/rm /tmp/src')


def test_remove_recursive(mock_run):
    from burlap.files import remove
    remove('/tmp/src', recursive=True)
    mock_run.assert_called_with('/bin/rm -r /tmp/src')

def test_enable_attribute():
    #from burlap.file import appendline
    from burlap.common import enable_attribute_or_dryrun, env
    
    env.hosts = ['localhost']
    env.host_string = 'localhost'
    
    fn = '/tmp/test.txt'
    
    # Add key/value when old exists commented
    open(fn, 'w').write('''# Test
#start_x=0
more_stuff=1
''')
    enable_attribute_or_dryrun(
        filename=fn,
        key='start_x',
        value='1',
    )
    content = open(fn).read()
    print('content:')
    print(content)
    assert '#start_x=0' not in content
    assert '#start_x=1' not in content
    assert 'start_x=0' not in content
    assert 'start_x=1' in content
    
    # Add key/value when none exists
    open(fn, 'w').write('''# Test
more_stuff=1
''')
    enable_attribute_or_dryrun(
        filename=fn,
        key='start_x',
        value='0',
    )
    content = open(fn).read()
    print('content:')
    print(content)
    assert '#start_x=0' not in content
    assert '#start_x=1' not in content
    assert 'start_x=1' not in content
    assert 'start_x=0' in content
    
    # Add key/value when uncommented exists
    open(fn, 'w').write('''# Test
start_x=1
more_stuff=1
''')
    enable_attribute_or_dryrun(
        filename=fn,
        key='start_x',
        value='0',
    )
    content = open(fn).read()
    print('content:')
    print(content)
    assert '#start_x=0' not in content
    assert '#start_x=1' not in content
    assert 'start_x=1' not in content
    assert 'start_x=0' in content
    
    # Add key/value when commented exists with spaces
    open(fn, 'w').write('''# Test
# start_x = 1
more_stuff=1
''')
    enable_attribute_or_dryrun(
        filename=fn,
        key='start_x',
        value='0',
    )
    content = open(fn).read()
    print('content:')
    print(content)
    assert '#start_x=0' not in content
    assert '#start_x=1' not in content
    assert 'start_x=1' not in content
    assert 'start_x=0' in content
    