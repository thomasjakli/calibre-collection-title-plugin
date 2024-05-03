from __future__ import unicode_literals, division, absolute_import, print_function

__license__   = 'GPL v3'
__copyright__ = '2024, IncrediblePineapple'

import six
import os, time, traceback, re

from calibre import CurrentDir, guess_type
from calibre.ebooks.chardet import strip_encoding_declarations
from calibre.ebooks.conversion.plumber import OptionValues
from calibre.ebooks.metadata.opf2 import OPF
from calibre.ebooks.metadata.meta import set_metadata
from calibre.ebooks.oeb.base import XPath
from calibre.customize.ui import apply_null_metadata
from calibre.libunzip import extract as zipextract
from calibre.ptempfile import TemporaryDirectory
from calibre.ebooks.oeb.polish.container import EpubContainer
from pkg_resources import packaging

from lxml import etree

def modify_epub(log, title, epub_path, calibre_opf_path, cover_path):
    start_time = time.time()
    modifier = BookModifier(log)
    new_book_path = modifier.process_book(title, epub_path, calibre_opf_path,
                                          cover_path)
    if new_book_path:
        log('ePub updated in %.2f seconds'%(time.time() - start_time))
    else:
        log('ePub not changed after %.2f seconds'%(time.time() - start_time))
    return new_book_path

class BookModifier(object):
    
    namespaces = {
        'opf': 'http://www.idpf.org/2007/opf',
        'dc': 'http://purl.org/dc/elements/1.1/'
    }

    def __init__(self, log):
        self.log = log

    def process_book(self, title, epub_path, calibre_opf_path, cover_path):
        self.log('  Modifying: ', epub_path)
        try:
            self._restore_metadata_from_opf(calibre_opf_path)

            # Extract the epub into a temp directory
            with TemporaryDirectory('_collection_titles') as tdir:
                with CurrentDir(tdir):
                    zipextract(epub_path, tdir)

                    # Use our own simplified wrapper around an ePub that will
                    # preserve the file structure and css
                    container = EpubContainer(epub_path, self.log, tdir=tdir)
                    is_modified = self._insert_collection_title(container)
                    if is_modified:
                        container.commit(epub_path)

            # Only return path to the ePub if we have changed it
            if is_modified:
                return epub_path
        except:
            self.log.exception('%s - ERROR: %s' %(title, traceback.format_exc()))
        finally:
            if calibre_opf_path and os.path.exists(calibre_opf_path):
                os.remove(calibre_opf_path)
            if cover_path and os.path.exists(cover_path):
                os.remove(cover_path)

    def _restore_metadata_from_opf(self, calibre_opf_path):
        '''
        Create an mi object from our copy of the latest Calibre metadata
        stored in an OPF, so that we can perform functions that update
        the book metadata, such as generating a new jacket.
        '''
        if calibre_opf_path and os.path.exists(calibre_opf_path):
            with open(calibre_opf_path, 'r') as f:
                calibre_opf = OPF(f, os.path.dirname(calibre_opf_path))
            self.mi = calibre_opf.to_book_metadata()

    def _insert_collection_title(self, container):
        collection = self.mi.get_all_user_metadata(False).get("#collection", None)
        # Should not happen... but whatevs
        if collection is None:
            return False
        
        opf = container.opf
        metadata = opf[0]
        version = opf.attrib["version"]
        if version is not None and packaging.version.parse(version) < packaging.version.parse("3.0"):
           self.log.warning("Epub is not version 3, skipping because multiple titles are not supported")
           return False
            
        titleElementName = etree.QName(BookModifier.namespaces['dc'], 'title')
        changed = False
        newPositionString = str(int(collection["#extra#"] or 0))
        newTitle = collection["#value#"] or ""
        isEmpty = newTitle == ""

        numExistingTitles = len(metadata.xpath("//dc:title", namespaces=BookModifier.namespaces))
        #self.log('Number of existing titles in metadata: ', numExistingTitles)
        titleId = "t" + str((numExistingTitles + 1))

        type_meta = next(iter(metadata.xpath("opf:meta[@property = 'title-type' and text() = 'collection']", namespaces=BookModifier.namespaces)), None)
        if type_meta is None and not isEmpty:
          self.log('Inserting new title-type meta for title', titleId)
          type_meta = etree.SubElement(metadata, 'meta')
          type_meta.attrib["refines"] = '#' + titleId
          type_meta.attrib["property"] = "title-type"
          type_meta.text = "collection"
          changed = True
        elif type_meta is not None:
          titleId = type_meta.attrib["refines"].strip("#")

        position_meta = next(iter(metadata.xpath("opf:meta[@property = 'group-position' and @refines = '#" + titleId + "']", namespaces=BookModifier.namespaces)), None)
        if position_meta is None and not isEmpty:
          self.log('Inserting new group-position meta for title', titleId)
          position_meta = etree.SubElement(metadata, 'meta')
          position_meta.attrib["refines"] = '#' + titleId
          position_meta.attrib["property"] = "group-position"
          changed = True

        titleElement = next(iter(metadata.xpath("dc:title[@id = '" + titleId + "']", namespaces=BookModifier.namespaces)), None)
        if titleElement is None and not isEmpty:
          self.log('Inserting new title', titleId)
          titleElement = etree.SubElement(metadata, titleElementName)
          titleElement.attrib["id"] = titleId
          changed = True
        
        if isEmpty:
          if type_meta is not None:
            self.log('Removing existing title-type meta for title', titleId)
            metadata.remove(type_meta)
            changed = True
          if position_meta is not None:
            self.log('Removing existing group-position meta for title', titleId)
            metadata.remove(position_meta)
            changed = True
          if titleElement is not None:
            self.log('Removing existing title', titleId)
            metadata.remove(titleElement)
            changed = True
        else:
          self.log('Updating group-position meta for title', titleId)
          changed = changed or (position_meta.text != newPositionString)
          position_meta.text = newPositionString
          
          self.log('Updating title', titleId)
          changed = changed or (titleElement.text != newTitle)
          titleElement.text = newTitle

        container.dirty(container.opf_name)

        if not changed:
          self.log('No changes made')

        return changed