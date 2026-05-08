# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_window.ui'
##
## Created by: Qt User Interface Compiler version 6.11.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMenuBar, QPushButton, QSizePolicy, QSpacerItem,
    QSplitter, QTabWidget, QTextEdit, QToolButton,
    QVBoxLayout, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1200, 800)
        self.actionNew = QAction(MainWindow)
        self.actionNew.setObjectName(u"actionNew")
        self.actionOpen = QAction(MainWindow)
        self.actionOpen.setObjectName(u"actionOpen")
        self.actionSave = QAction(MainWindow)
        self.actionSave.setObjectName(u"actionSave")
        self.actionExit = QAction(MainWindow)
        self.actionExit.setObjectName(u"actionExit")
        self.centralwidget = QSplitter(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.centralwidget.setOrientation(Qt.Orientation.Vertical)
        self.centralwidget.setHandleWidth(4)
        self.centralwidget.setChildrenCollapsible(False)
        self.topPanel = QSplitter(self.centralwidget)
        self.topPanel.setObjectName(u"topPanel")
        self.topPanel.setOrientation(Qt.Orientation.Horizontal)
        self.topPanel.setHandleWidth(4)
        self.topPanel.setChildrenCollapsible(False)
        self.activityBar = QWidget(self.topPanel)
        self.activityBar.setObjectName(u"activityBar")
        self.activityBar.setMinimumSize(QSize(40, 0))
        self.activityBar.setMaximumSize(QSize(40, 16777215))
        self.verticalLayoutActivity = QVBoxLayout(self.activityBar)
        self.verticalLayoutActivity.setSpacing(0)
        self.verticalLayoutActivity.setObjectName(u"verticalLayoutActivity")
        self.verticalLayoutActivity.setContentsMargins(0, 0, 0, 0)
        self.btnAndroid = QToolButton(self.activityBar)
        self.btnAndroid.setObjectName(u"btnAndroid")
        self.btnAndroid.setMinimumSize(QSize(40, 50))
        self.btnAndroid.setMaximumSize(QSize(40, 50))
        self.btnAndroid.setCheckable(True)
        self.btnAndroid.setChecked(True)

        self.verticalLayoutActivity.addWidget(self.btnAndroid)

        self.btnSearch = QToolButton(self.activityBar)
        self.btnSearch.setObjectName(u"btnSearch")
        self.btnSearch.setMinimumSize(QSize(40, 50))
        self.btnSearch.setMaximumSize(QSize(40, 50))
        self.btnSearch.setCheckable(True)

        self.verticalLayoutActivity.addWidget(self.btnSearch)

        self.btnGit = QToolButton(self.activityBar)
        self.btnGit.setObjectName(u"btnGit")
        self.btnGit.setMinimumSize(QSize(40, 50))
        self.btnGit.setMaximumSize(QSize(40, 50))
        self.btnGit.setCheckable(True)

        self.verticalLayoutActivity.addWidget(self.btnGit)

        self.btnRun = QToolButton(self.activityBar)
        self.btnRun.setObjectName(u"btnRun")
        self.btnRun.setMinimumSize(QSize(40, 50))
        self.btnRun.setMaximumSize(QSize(40, 50))
        self.btnRun.setCheckable(True)

        self.verticalLayoutActivity.addWidget(self.btnRun)

        self.btnExt = QToolButton(self.activityBar)
        self.btnExt.setObjectName(u"btnExt")
        self.btnExt.setMinimumSize(QSize(40, 50))
        self.btnExt.setMaximumSize(QSize(40, 50))
        self.btnExt.setCheckable(True)

        self.verticalLayoutActivity.addWidget(self.btnExt)

        self.spacerActivity = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayoutActivity.addItem(self.spacerActivity)

        self.btnAccount = QToolButton(self.activityBar)
        self.btnAccount.setObjectName(u"btnAccount")
        self.btnAccount.setMinimumSize(QSize(40, 50))
        self.btnAccount.setMaximumSize(QSize(40, 50))

        self.verticalLayoutActivity.addWidget(self.btnAccount)

        self.btnSettings = QToolButton(self.activityBar)
        self.btnSettings.setObjectName(u"btnSettings")
        self.btnSettings.setMinimumSize(QSize(40, 50))
        self.btnSettings.setMaximumSize(QSize(40, 50))

        self.verticalLayoutActivity.addWidget(self.btnSettings)

        self.topPanel.addWidget(self.activityBar)
        self.sidePanel = QWidget(self.topPanel)
        self.sidePanel.setObjectName(u"sidePanel")
        self.sidePanel.setMinimumSize(QSize(260, 0))
        self.verticalLayoutSide = QVBoxLayout(self.sidePanel)
        self.verticalLayoutSide.setSpacing(0)
        self.verticalLayoutSide.setObjectName(u"verticalLayoutSide")
        self.verticalLayoutSide.setContentsMargins(0, 0, 0, 0)
        self.tabConnect = QTabWidget(self.sidePanel)
        self.tabConnect.setObjectName(u"tabConnect")
        self.tabConnect.setTabsClosable(False)
        self.tabWifi = QWidget()
        self.tabWifi.setObjectName(u"tabWifi")
        self.verticalLayoutWifi = QVBoxLayout(self.tabWifi)
        self.verticalLayoutWifi.setSpacing(8)
        self.verticalLayoutWifi.setObjectName(u"verticalLayoutWifi")
        self.verticalLayoutWifi.setContentsMargins(10, 10, 10, 10)
        self.lblIp = QLabel(self.tabWifi)
        self.lblIp.setObjectName(u"lblIp")

        self.verticalLayoutWifi.addWidget(self.lblIp)

        self.editIp = QLineEdit(self.tabWifi)
        self.editIp.setObjectName(u"editIp")

        self.verticalLayoutWifi.addWidget(self.editIp)

        self.lblPort = QLabel(self.tabWifi)
        self.lblPort.setObjectName(u"lblPort")

        self.verticalLayoutWifi.addWidget(self.lblPort)

        self.editPort = QLineEdit(self.tabWifi)
        self.editPort.setObjectName(u"editPort")

        self.verticalLayoutWifi.addWidget(self.editPort)

        self.btnAutoIp = QPushButton(self.tabWifi)
        self.btnAutoIp.setObjectName(u"btnAutoIp")

        self.verticalLayoutWifi.addWidget(self.btnAutoIp)

        self.btnIpConnect = QPushButton(self.tabWifi)
        self.btnIpConnect.setObjectName(u"btnIpConnect")

        self.verticalLayoutWifi.addWidget(self.btnIpConnect)

        self.spacerWifi = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayoutWifi.addItem(self.spacerWifi)

        self.tabConnect.addTab(self.tabWifi, "")
        self.tabAdb = QWidget()
        self.tabAdb.setObjectName(u"tabAdb")
        self.verticalLayoutAdb = QVBoxLayout(self.tabAdb)
        self.verticalLayoutAdb.setSpacing(8)
        self.verticalLayoutAdb.setObjectName(u"verticalLayoutAdb")
        self.verticalLayoutAdb.setContentsMargins(10, 10, 10, 10)
        self.btnRefreshAdb = QPushButton(self.tabAdb)
        self.btnRefreshAdb.setObjectName(u"btnRefreshAdb")

        self.verticalLayoutAdb.addWidget(self.btnRefreshAdb)

        self.listAdbDevices = QListWidget(self.tabAdb)
        self.listAdbDevices.setObjectName(u"listAdbDevices")
        self.listAdbDevices.setMinimumSize(QSize(0, 120))

        self.verticalLayoutAdb.addWidget(self.listAdbDevices)

        self.btnAdbConnect = QPushButton(self.tabAdb)
        self.btnAdbConnect.setObjectName(u"btnAdbConnect")

        self.verticalLayoutAdb.addWidget(self.btnAdbConnect)

        self.spacerAdb = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)

        self.verticalLayoutAdb.addItem(self.spacerAdb)

        self.tabConnect.addTab(self.tabAdb, "")

        self.verticalLayoutSide.addWidget(self.tabConnect)

        self.lblStatus = QLabel(self.sidePanel)
        self.lblStatus.setObjectName(u"lblStatus")

        self.verticalLayoutSide.addWidget(self.lblStatus)

        self.topPanel.addWidget(self.sidePanel)
        self.tabWidget = QTabWidget(self.topPanel)
        self.tabWidget.setObjectName(u"tabWidget")
        self.tabWidget.setTabsClosable(True)
        self.tabWidget.setMovable(True)
        self.tab = QWidget()
        self.tab.setObjectName(u"tab")
        self.tabLayout = QVBoxLayout(self.tab)
        self.tabLayout.setSpacing(0)
        self.tabLayout.setObjectName(u"tabLayout")
        self.tabLayout.setContentsMargins(0, 0, 0, 0)
        self.videoWidget = QWidget(self.tab)
        self.videoWidget.setObjectName(u"videoWidget")

        self.tabLayout.addWidget(self.videoWidget)

        self.tabWidget.addTab(self.tab, "")
        self.topPanel.addWidget(self.tabWidget)
        self.centralwidget.addWidget(self.topPanel)
        self.outputPanel = QWidget(self.centralwidget)
        self.outputPanel.setObjectName(u"outputPanel")
        self.outputPanel.setMinimumSize(QSize(0, 80))
        self.verticalLayoutOutput = QVBoxLayout(self.outputPanel)
        self.verticalLayoutOutput.setSpacing(5)
        self.verticalLayoutOutput.setObjectName(u"verticalLayoutOutput")
        self.verticalLayoutOutput.setContentsMargins(5, 5, 5, 5)
        self.horizontalLayoutOutput = QHBoxLayout()
        self.horizontalLayoutOutput.setObjectName(u"horizontalLayoutOutput")
        self.btnClear = QPushButton(self.outputPanel)
        self.btnClear.setObjectName(u"btnClear")

        self.horizontalLayoutOutput.addWidget(self.btnClear)

        self.spacerOutput = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self.horizontalLayoutOutput.addItem(self.spacerOutput)


        self.verticalLayoutOutput.addLayout(self.horizontalLayoutOutput)

        self.textOutput = QTextEdit(self.outputPanel)
        self.textOutput.setObjectName(u"textOutput")
        self.textOutput.setReadOnly(True)

        self.verticalLayoutOutput.addWidget(self.textOutput)

        self.centralwidget.addWidget(self.outputPanel)
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1200, 33))
        self.menuFile = QMenu(self.menubar)
        self.menuFile.setObjectName(u"menuFile")
        MainWindow.setMenuBar(self.menubar)

        self.menubar.addAction(self.menuFile.menuAction())
        self.menuFile.addAction(self.actionNew)
        self.menuFile.addAction(self.actionOpen)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionSave)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionExit)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"\u7f16\u8f91\u5668", None))
        self.actionNew.setText(QCoreApplication.translate("MainWindow", u"\u65b0\u5efa(&N)", None))
#if QT_CONFIG(shortcut)
        self.actionNew.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+N", None))
#endif // QT_CONFIG(shortcut)
        self.actionOpen.setText(QCoreApplication.translate("MainWindow", u"\u6253\u5f00(&O)", None))
#if QT_CONFIG(shortcut)
        self.actionOpen.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+O", None))
#endif // QT_CONFIG(shortcut)
        self.actionSave.setText(QCoreApplication.translate("MainWindow", u"\u4fdd\u5b58(&S)", None))
#if QT_CONFIG(shortcut)
        self.actionSave.setShortcut(QCoreApplication.translate("MainWindow", u"Ctrl+S", None))
#endif // QT_CONFIG(shortcut)
        self.actionExit.setText(QCoreApplication.translate("MainWindow", u"\u9000\u51fa(&X)", None))
        self.centralwidget.setStyleSheet(QCoreApplication.translate("MainWindow", u"QSplitter::handle { background-color: #444444; }", None))
        self.topPanel.setStyleSheet(QCoreApplication.translate("MainWindow", u"QSplitter::handle { background-color: #444444; }", None))
        self.activityBar.setStyleSheet(QCoreApplication.translate("MainWindow", u"background-color: #333333;", None))
#if QT_CONFIG(tooltip)
        self.btnAndroid.setToolTip(QCoreApplication.translate("MainWindow", u"Android \u8fde\u63a5", None))
#endif // QT_CONFIG(tooltip)
        self.btnAndroid.setStyleSheet(QCoreApplication.translate("MainWindow", u"QToolButton { border: none; color: #cccccc; font-size: 18px; }\n"
"QToolButton:hover { background-color: #505050; }\n"
"QToolButton:checked { background-color: #505050; border-left: 3px solid #007acc; }", None))
        self.btnAndroid.setText(QCoreApplication.translate("MainWindow", u"\U0001f4f1", None))
#if QT_CONFIG(tooltip)
        self.btnSearch.setToolTip(QCoreApplication.translate("MainWindow", u"\u6587\u4ef6", None))
#endif // QT_CONFIG(tooltip)
        self.btnSearch.setStyleSheet(QCoreApplication.translate("MainWindow", u"QToolButton { border: none; color: #cccccc; font-size: 18px; }\n"
"QToolButton:hover { background-color: #505050; }\n"
"QToolButton:checked { background-color: #505050; border-left: 3px solid #007acc; }", None))
        self.btnSearch.setText(QCoreApplication.translate("MainWindow", u"\U0001f4c1", None))
#if QT_CONFIG(tooltip)
        self.btnGit.setToolTip(QCoreApplication.translate("MainWindow", u"\u6e90\u4ee3\u7801\u7ba1\u7406", None))
#endif // QT_CONFIG(tooltip)
        self.btnGit.setStyleSheet(QCoreApplication.translate("MainWindow", u"QToolButton { border: none; color: #cccccc; font-size: 18px; }\n"
"QToolButton:hover { background-color: #505050; }\n"
"QToolButton:checked { background-color: #505050; border-left: 3px solid #007acc; }", None))
        self.btnGit.setText(QCoreApplication.translate("MainWindow", u"\U0001f33f", None))
#if QT_CONFIG(tooltip)
        self.btnRun.setToolTip(QCoreApplication.translate("MainWindow", u"\u8fd0\u884c\u548c\u8c03\u8bd5", None))
#endif // QT_CONFIG(tooltip)
        self.btnRun.setStyleSheet(QCoreApplication.translate("MainWindow", u"QToolButton { border: none; color: #cccccc; font-size: 18px; }\n"
"QToolButton:hover { background-color: #505050; }\n"
"QToolButton:checked { background-color: #505050; border-left: 3px solid #007acc; }", None))
        self.btnRun.setText(QCoreApplication.translate("MainWindow", u"\u25b6", None))
#if QT_CONFIG(tooltip)
        self.btnExt.setToolTip(QCoreApplication.translate("MainWindow", u"\u6269\u5c55", None))
#endif // QT_CONFIG(tooltip)
        self.btnExt.setStyleSheet(QCoreApplication.translate("MainWindow", u"QToolButton { border: none; color: #cccccc; font-size: 18px; }\n"
"QToolButton:hover { background-color: #505050; }\n"
"QToolButton:checked { background-color: #505050; border-left: 3px solid #007acc; }", None))
        self.btnExt.setText(QCoreApplication.translate("MainWindow", u"\U0001f9e9", None))
#if QT_CONFIG(tooltip)
        self.btnAccount.setToolTip(QCoreApplication.translate("MainWindow", u"\u5e10\u6237", None))
#endif // QT_CONFIG(tooltip)
        self.btnAccount.setStyleSheet(QCoreApplication.translate("MainWindow", u"QToolButton { border: none; color: #cccccc; font-size: 18px; }\n"
"QToolButton:hover { background-color: #505050; }", None))
        self.btnAccount.setText(QCoreApplication.translate("MainWindow", u"\U0001f464", None))
#if QT_CONFIG(tooltip)
        self.btnSettings.setToolTip(QCoreApplication.translate("MainWindow", u"\u7ba1\u7406", None))
#endif // QT_CONFIG(tooltip)
        self.btnSettings.setStyleSheet(QCoreApplication.translate("MainWindow", u"QToolButton { border: none; color: #cccccc; font-size: 18px; }\n"
"QToolButton:hover { background-color: #505050; }", None))
        self.btnSettings.setText(QCoreApplication.translate("MainWindow", u"\u2699", None))
        self.sidePanel.setStyleSheet(QCoreApplication.translate("MainWindow", u"background-color: #252526; color: #cccccc;", None))
        self.lblIp.setText(QCoreApplication.translate("MainWindow", u"IP \u5730\u5740", None))
        self.editIp.setStyleSheet(QCoreApplication.translate("MainWindow", u"QLineEdit { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 4px; }", None))
        self.editIp.setPlaceholderText(QCoreApplication.translate("MainWindow", u"192.168.1.100", None))
        self.lblPort.setText(QCoreApplication.translate("MainWindow", u"\u7aef\u53e3", None))
        self.editPort.setStyleSheet(QCoreApplication.translate("MainWindow", u"QLineEdit { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 4px; }", None))
        self.editPort.setText(QCoreApplication.translate("MainWindow", u"5555", None))
        self.btnAutoIp.setStyleSheet(QCoreApplication.translate("MainWindow", u"QPushButton { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 6px; }\n"
"QPushButton:hover { background-color: #505050; }", None))
        self.btnAutoIp.setText(QCoreApplication.translate("MainWindow", u"\u81ea\u52a8\u83b7\u53d6 IP", None))
        self.btnIpConnect.setStyleSheet(QCoreApplication.translate("MainWindow", u"QPushButton { background-color: #0e639c; color: white; border: none; padding: 6px; }\n"
"QPushButton:hover { background-color: #1177bb; }", None))
        self.btnIpConnect.setText(QCoreApplication.translate("MainWindow", u"IP \u8fde\u63a5", None))
        self.tabConnect.setTabText(self.tabConnect.indexOf(self.tabWifi), QCoreApplication.translate("MainWindow", u"WiFi", None))
        self.btnRefreshAdb.setStyleSheet(QCoreApplication.translate("MainWindow", u"QPushButton { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 6px; }\n"
"QPushButton:hover { background-color: #505050; }", None))
        self.btnRefreshAdb.setText(QCoreApplication.translate("MainWindow", u"\u5237\u65b0\u8bbe\u5907", None))
        self.listAdbDevices.setStyleSheet(QCoreApplication.translate("MainWindow", u"QListWidget { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 4px; }\n"
"QListWidget::item { padding: 6px; }\n"
"QListWidget::item:selected { background-color: #0e639c; color: white; }\n"
"QListWidget::item:hover { background-color: #2a2d2e; }", None))
        self.btnAdbConnect.setStyleSheet(QCoreApplication.translate("MainWindow", u"QPushButton { background-color: #0e639c; color: white; border: none; padding: 6px; }\n"
"QPushButton:hover { background-color: #1177bb; }", None))
        self.btnAdbConnect.setText(QCoreApplication.translate("MainWindow", u"\u8fde\u63a5\u9009\u4e2d\u8bbe\u5907", None))
        self.tabConnect.setTabText(self.tabConnect.indexOf(self.tabAdb), QCoreApplication.translate("MainWindow", u"ADB", None))
        self.lblStatus.setStyleSheet(QCoreApplication.translate("MainWindow", u"color: #888888; padding: 5px 10px;", None))
        self.lblStatus.setText(QCoreApplication.translate("MainWindow", u"\u72b6\u6001: \u672a\u8fde\u63a5", None))
        self.videoWidget.setStyleSheet(QCoreApplication.translate("MainWindow", u"background-color: #000000;", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab), QCoreApplication.translate("MainWindow", u"\u6295\u5c4f", None))
        self.outputPanel.setStyleSheet(QCoreApplication.translate("MainWindow", u"background-color: #252526;", None))
        self.btnClear.setText(QCoreApplication.translate("MainWindow", u"\u6e05\u9664", None))
        self.textOutput.setStyleSheet(QCoreApplication.translate("MainWindow", u"QTextEdit { background-color: #1e1e1e; color: #d4d4d4; border: none; }", None))
        self.textOutput.setPlainText(QCoreApplication.translate("MainWindow", u"\u7cfb\u7edf\u542f\u52a8\u6210\u529f", None))
        self.textOutput.setPlaceholderText(QCoreApplication.translate("MainWindow", u"\u8f93\u51fa\u65e5\u5fd7...", None))
        self.menuFile.setTitle(QCoreApplication.translate("MainWindow", u"\u6587\u4ef6(&F)", None))
    # retranslateUi

