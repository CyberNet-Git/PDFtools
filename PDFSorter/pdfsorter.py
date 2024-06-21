import os
import sys
import pathlib

from PyQt6 import uic, QtGui, QtCore
from PyQt6.QtWidgets import QWidget,  QApplication, QMainWindow, QFileDialog, QGraphicsScene,\
                            QGraphicsPixmapItem, QGraphicsItem, QListWidgetItem, QLayout
from PyQt6.QtGui import QPixmap, QIcon, QGuiApplication, QWindow
from PyQt6.QtSvg import QSvgRenderer, QSvgGenerator
from PyQt6.QtSvgWidgets import QGraphicsSvgItem, QSvgWidget

import random


try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

import pymupdf

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


def get_download_path():
    """Returns the default downloads path for linux or windows"""
    if os.name == 'nt':
        import winreg
        sub_key = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders'
        downloads_guid = '{374DE290-123F-4565-9164-39C4925E467B}'
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
            location = winreg.QueryValueEx(key, downloads_guid)[0]
        return location
    else:
        return os.path.join(os.path.expanduser('~'), 'downloads')

def get_scan_path():        
    return '.\IN'


class MyWindow(QMainWindow, FileSystemEventHandler):
    def __init__(self, parent=None):
        super(MyWindow, self).__init__(parent)
        
        Form, Base = uic.loadUiType('pdfsorter.ui')
        self.ui = Form()
        self.ui.setupUi(self)
        self.statusBar()
        
        self.hide_help()
        
        self.settings = QtCore.QSettings()
        
        self.observer = Observer()
        
        self.srcDir = self.settings.value('srcdir')
        if self.srcDir == '' or self.srcDir is None:
            self.srcDir = './'
            self.settings.setValue('srcdir',self.srcDir)
        self.update_srcdir_view()
        self.ui.label_srcdir.setText(self.settings.value('srcdir'))
        self.srcdir_obs = self.observer.schedule(self, path=self.srcDir, recursive=False)
        
        self.dstDir = self.settings.value('dstdir')
        if self.dstDir == '' or self.dstDir is None:
            self.dstDir = './'
            self.settings.setValue('dstdir',self.dstDir)
        self.update_dstdir_view()
        self.ui.label_dstdir.setText(self.settings.value('dstdir'))

        self.ui.tbSrcDir.clicked.connect(self.slot_srcdir_open)
        self.ui.tbDstDir.clicked.connect(self.slot_dstdir_open)
        self.ui.action_4.triggered.connect(self.display_help)
        self.ui.pbHideHelp.clicked.connect(self.hide_help)
        
        self.dstdir_obs = self.observer.schedule(self, path=self.dstDir, recursive=False)

        self.observer.start()
        

    def adjust_size_pos(self):
    """ place and resize main window accordig to display device resolution """
        r = QGuiApplication.primaryScreen().availableGeometry()
        r.adjust(0,0,-80,-40)
        r.moveCenter(QGuiApplication.primaryScreen().availableGeometry().center())
        self.setGeometry(r)
        self.move(r.topLeft())

        
    def hide_layout(self, layout):
    """ hides all widgets of desired layout """
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, QWidget):
                widget.hide()
            if isinstance(item, QLayout):
                self.hide_layout(item)

    def show_layout(self, layout):
    """ shows all widgets of desired layout """
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget()
            if isinstance(widget, QWidget):
                widget.show()
            if isinstance(item, QLayout):
                self.show_layout(item)

    def display_help(self):
        self.hide_layout(self.ui.workLayout)
        self.show_layout(self.ui.helpLayout)

    def hide_help(self):
        self.hide_layout(self.ui.helpLayout)
        self.show_layout(self.ui.workLayout)

    
    def opendir(self):
        try:
            self.fd
        except:
            self.fd = QFileDialog(self)
        finally:
            self.fd.setFileMode(QFileDialog.FileMode.Directory)
            if self.fd.exec():
                dir = self.fd.selectedFiles()[0]
            else:
                dir = get_download_path()
            return dir
    
    def slot_srcdir_open(self, arg1):
        self.srcDir = self.opendir()
        self.settings.setValue('srcdir',self.srcDir)
        self.update_srcdir_view()
        self.ui.label_srcdir.setText(self.settings.value('srcdir'))
        self.observer.unschedule(self.srcdir_obs)
        self.srcdir_obs = self.observer.schedule(self, path=self.srcDir, recursive=False) 

    def slot_dstdir_open(self, arg1):
        self.dstDir = self.opendir()
        self.settings.setValue('dstdir',self.dstDir)
        self.update_dstdir_view()
        self.ui.label_dstdir.setText(self.settings.value('dstdir'))
        self.observer.unschedule(self.dstdir_obs)
        self.dstdir_obs = self.observer.schedule(self, path=self.dstDir, recursive=False) 

    def update_srcdir_view(self):
        files = os.listdir(self.srcDir)
        self.ui.listWidgetL.clear()
        self.ui.listWidgetL.addItems(files)

    def update_dstdir_view(self):
        files = os.listdir(self.dstDir)
        self.ui.listWidgetR.clear()
        self.ui.listWidgetR.addItems(files)

    def log(self, msgs):
    """ just log msgs to a list widget """
        self.ui.logWidget.addItems([msgs])
    
    def process_file(self, fname):
    """ main worker - page sorter """
        try:
            p = pathlib.Path(fname)
            self.log(f'Обрабатываем файл {p.resolve()}')
            outfn = pathlib.Path(self.dstDir) / p.name
            self.log(f'Запишем в файл {outfn.resolve()}')
            if p.resolve() == outfn.resolve():
                self.log(f'Нельзя записать в один и тот же файл {outfn.resolve()}. Останавливаю обработку.')
                self.log(f'Скоррктируйте исходную папку и папку назначения. Они должны различаться!')
                return
            doc = pymupdf.open(p.resolve())
            self.log(f'Разделов {doc.chapter_count}')
            for i in range(doc.chapter_count):
                pc = doc.chapter_page_count(i)
                self.log(f'Раздел {i} - {pc} страниц')
            chapter = 0
            half = doc.chapter_page_count(chapter) // 2
            one = doc.chapter_page_count(chapter) % 2
            self.log(f'half={half}, one={one}')

            for i in range(0, half - 1 ):
                self.log(f'{half+i} -> {i*2 + 1}')
                doc.move_page(half + i , i*2 + 1)
                
            doc.save(outfn.resolve())
        except Exception as e:
            self.log(f'Ошибка {e.msg}')
            
    def on_any_event(self, event):
    """ virtual method for FileSystemEventHandler funtionality
        occures when any event on watched directory fires  """
        self.statusBar().showMessage( f'{event.event_type}, {event.src_path}' )
        
        p = pathlib.Path(event.src_path)
        
        if p.is_relative_to(self.srcDir):
            self.update_srcdir_view()
            self.log(f'SRC {event.event_type}, {event.src_path}')
            if event.event_type == 'modified':
                self.process_file(event.src_path)
            
        if p.is_relative_to(self.dstDir):
            self.update_dstdir_view()
            self.log(f'DST {event.event_type}, {event.src_path}')
        
    def on_modified(self, event):
        print("on_modified", event.src_path)
        #self.statusBar().showMessage(event.src_path)

    
QApplication.setOrganizationName("CyberNet-Git")
QApplication.setOrganizationDomain("sagdatmar.ru")
QApplication.setApplicationName("PDFSorter")  

app = QApplication(sys.argv)
window = MyWindow()
window.show()
window.adjust_size_pos()
retval = app.exec()
window.observer.stop()
sys.exit(retval)
