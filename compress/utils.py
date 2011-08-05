import os
import re
import tempfile
import gzip

from django.conf import settings as django_settings
from django.utils.http import urlquote
from django.dispatch import dispatcher

from compress.conf import settings
from compress.signals import css_filtered, js_filtered

def get_class(class_string):
    """
    Convert a string version of a function name to the callable object.
    """

    if not hasattr(class_string, '__bases__'):

        try:
            class_string = class_string.encode('ascii')
            mod_name, class_name = get_mod_func(class_string)
            if class_name != '':
                class_string = getattr(__import__(mod_name, {}, {}, ['']), class_name)
        except (ImportError, AttributeError):
            raise Exception('Failed to import filter %s' % class_string)

    return class_string

def get_mod_func(callback):
    """
    Converts 'django.views.news.stories.story_detail' to
    ('django.views.news.stories', 'story_detail')
    """

    try:
        dot = callback.rindex('.')
    except ValueError:
        return callback, ''
    return callback[:dot], callback[dot+1:]

def needs_update(output_file, source_files, verbosity=0):
    """
    Scan the source files for changes and returns True if the output_file needs to be updated.
    """

    version = get_version(source_files)

    on = get_output_filename(output_file, version)
    compressed_file_full = media_root(on)

    if not os.path.exists(compressed_file_full):
        return True, version

    update_needed = getattr(get_class(settings.COMPRESS_VERSIONING)(), 'needs_update')(output_file, source_files, version)
    return update_needed

def media_root(filename):
    """
    Return the full path to ``filename``. ``filename`` is a relative path name in MEDIA_ROOT
    """
    return os.path.join(django_settings.COMPRESS_MEDIA_ROOT, filename)

def media_url(url, prefix=None):
    if prefix:
        return prefix + urlquote(url)
    return django_settings.MEDIA_URL + urlquote(url)

def concat(filenames, separator=''):
    """
    Concatenate the files from the list of the ``filenames``, ouput separated with ``separator``.
    """
    r = ''
    for filename in filenames:
        fd = open(media_root(filename), 'rb')
        r += fd.read()
        r += separator
        fd.close()
    return r

def max_mtime(files):
    return int(max([os.stat(media_root(f)).st_mtime for f in files]))

def save_file(filename, contents):
    dirname = os.path.dirname(media_root(filename))
    if not os.path.exists(dirname):
        os.makedirs(dirname)
    fd = open(media_root(filename), 'wb+')
    fd.write(contents)
    fd.close()
    fdgz = gzip.open(media_root(filename+".gz"), 'wb+')
    fdgz.write(contents)
    fdgz.close()

def get_output_filename(filename, version):
    if settings.COMPRESS_VERSION and version is not None:
        return filename.replace(settings.COMPRESS_VERSION_PLACEHOLDER, version)
    else:
        return filename.replace(settings.COMPRESS_VERSION_PLACEHOLDER, settings.COMPRESS_VERSION_DEFAULT)

def get_version(source_files, verbosity=0):
    version = getattr(get_class(settings.COMPRESS_VERSIONING)(), 'get_version')(source_files)
    return version

def get_version_from_file(path, filename):
    regex = re.compile(r'^%s$' % (get_output_filename(settings.COMPRESS_VERSION_PLACEHOLDER.join([re.escape(part) for part in filename.split(settings.COMPRESS_VERSION_PLACEHOLDER)]), r'([A-Za-z0-9]+)')))
    for f in os.listdir(path):
        result = regex.match(f)
        if result and result.groups():
            return result.groups()[0]

def remove_files(path, filename, verbosity=0):
    regex = re.compile(r'^%s$' % (os.path.basename(get_output_filename(settings.COMPRESS_VERSION_PLACEHOLDER.join([re.escape(part) for part in filename.split(settings.COMPRESS_VERSION_PLACEHOLDER)]), r'[A-Za-z0-9]+'))))
    if os.path.exists(path):
        for f in os.listdir(path):
            if regex.match(f):
                if verbosity >= 1:
                    print "Removing outdated file %s" % f

                os.unlink(os.path.join(path, f))
                try:
                    os.unlink(os.path.join(path, f+".gz"))
                except:
                    pass

def filter_common(obj, verbosity, filters, attr, separator, signal, version=None):
    output = concat(obj['source_filenames'], separator)

    filename = get_output_filename(obj['output_filename'], get_version(obj['source_filenames']))

    if settings.COMPRESS_VERSION:
        remove_files(os.path.dirname(media_root(filename)), obj['output_filename'], verbosity)

    if verbosity >= 1:
        print "Saving %s" % filename

    for f in filters:
        output = getattr(get_class(f)(verbose=(verbosity >= 2)), attr)(output)

    #if(version is not None):
    path_name = media_root("webroot/static/js/")
    version = get_version_from_file(path_name, "webglviewer.r?.js")
    output = output.replace("{{ webgljsfileversion }}", str(version))
    version = get_version_from_file(path_name, "htmlviewer.r?.js")
    output = output.replace("{{ htmljsfileversion }}", str(version))
    version = get_version_from_file(path_name, "flashviewer.r?.js")
    output = output.replace("{{ flashjsfileversion }}", str(version))


    save_file(filename, output)
    signal.send(None)

def filter_css(css, verbosity=0):
    return filter_common(css, verbosity, filters=settings.COMPRESS_CSS_FILTERS, attr='filter_css', separator='', signal=css_filtered)

def filter_js(js, version, verbosity=0):
    return filter_common(js, verbosity, filters=settings.COMPRESS_JS_FILTERS, attr='filter_js', separator='', signal=js_filtered, version=version)
