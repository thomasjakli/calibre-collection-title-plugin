from __future__ import unicode_literals, division, absolute_import, print_function

__license__   = 'GPL v3'
__copyright__ = '2011, Grant Drake'

import six
import os, traceback
try:
    from qt.core import (QVBoxLayout, QLabel, QCheckBox, QGridLayout,
                      QGroupBox, Qt, QDialogButtonBox, QWidget,
                      QProgressDialog, QTimer, QScrollArea)
except ImportError:
    from PyQt5.Qt import (QVBoxLayout, QLabel, QCheckBox, QGridLayout,
                      QGroupBox, Qt, QDialogButtonBox, QWidget,
                      QProgressDialog, QTimer, QScrollArea)

try:
    load_translations()
except NameError:
    pass # load_translations() added in calibre 1.9

# QWidget and QScrollArea added to support scrolling dialog box

from calibre.ebooks.metadata import authors_to_string
from calibre.gui2 import gprefs, warning_dialog, error_dialog
from calibre.gui2.convert.metadata import create_opf_file, create_cover_file
from calibre.ptempfile import remove_dir
from calibre.utils.config_base import tweaks

class QueueProgressDialog(QProgressDialog):

    def __init__(self, gui, book_epubs, tdir, queue, db):
        QProgressDialog.__init__(self, _('Working')+'...', _('Cancel'), 0, len(book_epubs), gui)
        self.setWindowTitle(_('Queueing books for inserting collection titles'))
        self.setMinimumWidth(500)
        self.book_epubs, self.tdir, self.queue, self.db = \
            book_epubs, tdir, queue, db
        self.gui = gui
        self.i, self.bad, self.books_to_modify = 0, [], []
        # QTimer workaround on Win 10 on first go for Win10/Qt6 users not displaying dialog properly.
        QTimer.singleShot(100, self.do_book)
        self.exec_()

    def do_book(self):
        book_id = self.book_epubs[self.i]
        self.i += 1

        try:
            mi, opf_file = create_opf_file(self.db, book_id)
            self.setLabelText(_('Queueing')+' '+mi.title)
            cover_file = create_cover_file(self.db, book_id)
            cover_file_name = cover_file.name if cover_file else None
            authors = authors_to_string(self._authors_to_list(self.db, book_id))
            # Copy the book to the temp directory, using book id as filename
            epub_file = os.path.join(self.tdir, '%d.epub'%book_id)
            with open(epub_file, 'w+b') as f:
                self.db.copy_format_to(book_id, 'EPUB', f, index_is_id=True)
            self.books_to_modify.append((book_id, mi.title, authors, epub_file,
                                         opf_file.name, cover_file_name))
        except:
            traceback.print_exc()
            self.bad.append(book_id)

        self.setValue(self.i)
        if self.i >= len(self.book_epubs):
            return self.do_queue()
        else:
            QTimer.singleShot(0, self.do_book)

    def do_queue(self):
        if self.gui is None:
            # There is a nasty QT bug with the timers/logic above which can
            # result in the do_queue method being called twice
            return
        self.hide()
        if self.bad != []:
            res = []
            for book_id in self.bad:
                title = self.db.title(book_id, True)
                res.append('%s'%title)
            msg = '%s' % '\n'.join(res)
            warning_dialog(self.gui, _('Could not modify ePub for some books'),
                _('Could not modify %d of %d books, because no ePub '
                'source format was found.') % (len(res), len(self.book_epubs)),
                msg).exec_()
        self.gui = None
        self.db = None
        # Queue a job to process these ePub books
        self.queue(self.tdir, self.books_to_modify)

    def _authors_to_list(self, db, book_id):
        authors = db.authors(book_id, index_is_id=True)
        if authors:
            return [a.strip().replace('|',',') for a in authors.split(',')]
        return []


class AddBooksProgressDialog(QProgressDialog):

    def __init__(self, gui, modified_epubs, tdir):
        self.total_count = len(modified_epubs)
        QProgressDialog.__init__(self, _('Working')+'...', _('Cancel'), 0, self.total_count, gui)
        self.setWindowTitle(_('Adding %d modified ePubs')% self.total_count +'...' )
        self.setMinimumWidth(500)
        self.modified_epubs, self.tdir = modified_epubs, tdir
        self.book_ids = list(modified_epubs.keys())
        self.gui = gui
        self.db = self.gui.current_db
        self.i = 0
        # QTimer workaround on Win 10 on first go for Win10/Qt6 users not displaying dialog properly.
        QTimer.singleShot(100, self.do_book_check)
        self.exec_()
        if self.db:
            self.do_close()

    def do_book_check(self):
        if self.i >= self.total_count:
            return self.do_close()
        book_id = self.book_ids[self.i]
        epub_path = self.modified_epubs[book_id]
        self.i += 1

        title = self.db.title(book_id, index_is_id=True)
        self.setLabelText(_('Adding')+': '+title)

        formats = self.db.formats(book_id, index_is_id=True)
        if tweaks['save_original_format_when_polishing'] and 'ORIGINAL_EPUB' not in formats:
            self.db.save_original_format(book_id, 'EPUB', notify=False)
        # Add the epub back, causing the size information to be updated
        self.db.add_format(book_id, 'EPUB', open(epub_path, 'rb'), index_is_id=True)
        self.setValue(self.i)

        QTimer.singleShot(0, self.do_book_check)

    def do_close(self):
        self.hide()
        self.db.update_last_modified(self.book_ids)
        remove_dir(self.tdir)
        self.gui.status_bar.show_message(_('ePub files updated'), 3000)
        self.gui = None
        self.db = None
