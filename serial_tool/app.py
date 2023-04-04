import logging
from functools import partial
import os
import sys
import time
import traceback
import webbrowser
from typing import List, Optional, Tuple

from serial import serialutil
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

import struct
import serial_tool
from serial_tool.defines import base
from serial_tool.defines import colors
from serial_tool.defines import ui_defs
from serial_tool import cmd_args
from serial_tool import models
from serial_tool import cfg_hdlr
from serial_tool import serial_hdlr
from serial_tool import communication
from serial_tool import setup_dialog
from serial_tool import paths
from serial_tool import validators
from serial_tool.gui.gui import Ui_root
from PyQt5.QtWidgets import *

import cantools


class Gui(QtWidgets.QMainWindow):
    sig_write = QtCore.pyqtSignal(str, str)
    sig_warning = QtCore.pyqtSignal(str, str)
    sig_error = QtCore.pyqtSignal(str, str)

    sig_close = QtCore.pyqtSignal()
    conf_1 = 0
    conf_2 = 0
    conf_3 = 0
    conf_4 = 0
    conf_5 = 0
    conf_6 = 0
    conf_7 = 0
    conf_8 = 0
    conf_9 = 0
    canID = 0

    def __init__(self, args: cmd_args.SerialToolArgs) -> None:
        """Main Serial Tool application window."""
        QtWidgets.QMainWindow.__init__(self)

        self.args = args

        self.ui = Ui_root()
        self.ui.setupUi(self)
        self._set_taskbar_icon()
        sys.excepthook = self._app_exc_handler

        # create lists of all similar items
        self.ui_data_fields: Tuple[QtWidgets.QLineEdit, ...] = (
            self.ui.lineEbit_1_No_of_cells,
            self.ui.lineEdit_2_No_of_cells_parallel,
            self.ui.lineEdit_3_No_of_Slaves,
            self.ui.lineEdit_4_Contactor_cut_off_timer,
            self.ui.lineEdit_5_Contactor_on_timer,
            self.ui.lineEdit_6_Rated_cell_capacity,
            self.ui.lineEdit_7_Cell_under_voltage_cutoff,
            self.ui.lineEdit_8_Cell_under_voltage_recovery,
            self.ui.lineEdit_9_Cell_over_voltage_cutoff,
            self.ui.lineEdit_10_Cell_over_voltage_recovery,
            self.ui.lineEdit_11_Pack_UV_cutoff,
            self.ui.lineEdit_12_Pack_UV_recovery,
            self.ui.lineEdit_13_Pack_OV_cutoff,
            self.ui.lineEdit_14_Pack_OV_recovery,
            self.ui.lineEdit_15_Charger_current_cutoff,
            self.ui.lineEdit_16_Charger_current_recovery,
            self.ui.lineEdit_17_Charger_over_temperature_cutoff,
            self.ui.lineEdit_18_Charger_over_temperature_recovery,
            self.ui.lineEdit_19_Discharging_current_cutoff,
            self.ui.lineEdit_20_Discharging_current_recovery,
            self.ui.lineEdit_21_Charging_under_temperature_cutoff,
            self.ui.lineEdit_22_Charging_under_temperature_recovery,
            self.ui.lineEdit_23_Discharging_over_temperature_cutoff,
            self.ui.lineEdit_24_Discharging_over_temperature_recovery,
            self.ui.lineEdit_25_Discharging_under_temperature_cutoff,
            self.ui.lineEdit_26_Discharging_under_temperature_recovery,
            self.ui.lineEdit_27_Start_cell_balancing_voltage,
            self.ui.lineEdit_28_Balancing_delta_difference,
            self.ui.lineEdit_29_AH_charge_discharge,
            self.ui.lineEdit_30_Rated_cell_capacity,
            self.ui.lineEdit_31_Short_circuit_current,

        )
        self.ui_data_send_buttons: Tuple[QtWidgets.QPushButton, ...] = (
            self.ui.PB_sendSequence1,

        )


        self._seq_threads: List[Optional[QtCore.QThread]] = [
                                                                None
                                                            ] * ui_defs.NUM_OF_SEQ_CHANNELS  # threads of sequence handlers
        self._seq_tx_workers: List[Optional[communication.TxDataSequenceHdlr]] = [
                                                                                     None
                                                                                 ] * ui_defs.NUM_OF_SEQ_CHANNELS  # actual sequence handlers

        self.ui.RB_GROUP_outputRepresentation.setId(
            self.ui.RB_outputRepresentationString, models.OutputRepresentation.STRING
        )
        self.ui.RB_GROUP_outputRepresentation.setId(
            self.ui.RB_outputRepresentationIntList, models.OutputRepresentation.INT_LIST
        )
        self.ui.RB_GROUP_outputRepresentation.setId(
            self.ui.RB_outputRepresentationHexList, models.OutputRepresentation.HEX_LIST
        )
        self.ui.RB_GROUP_outputRepresentation.setId(
            self.ui.RB_outputRepresentationAsciiList, models.OutputRepresentation.ASCII_LIST
        )

        self._signals = models.SharedSignalsContainer(self.sig_write, self.sig_warning, self.sig_error)

        # prepare data and port handlers
        self.data_cache = models.RuntimeDataCache()
        print("data_cache" + str(self.data_cache))
        self.ser_port = serial_hdlr.SerialPort(self.data_cache.serial_settings)
        print(self.ser_port)
        self.port_hdlr = communication.PortHdlr(self.data_cache.serial_settings, self.ser_port)


        self._last_rx_event_timestamp = time.time()
        # if true, log window is currently displaying RX data (to be used with '\n on RX data')
        self._display_rx_data = True

        self.cfg_hdlr = cfg_hdlr.ConfigurationHdlr(self.data_cache, self._signals)

        # init app and gui
        self.connect_signals_to_slots()
        self.connect_update_signals_to_slots()
        self.connect_app_signals_to_slots()

        self.init_gui()

        self.raise_()

    def _set_taskbar_icon(self) -> None:
        # windows specific: https://stackoverflow.com/a/27872625/9200430
        if os.name == "nt":
            import ctypes

            app_id = "damogranlabs.serialtool"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)

    def connect_signals_to_slots(self) -> None:
        # save/load dialog
        self.ui.PB_fileMenu_newConfiguration.triggered.connect(self.on_file_create_new_cfg)
        self.ui.PB_fileMenu_saveConfiguration.triggered.connect(self.on_file_save_cfg)
        self.ui.PB_fileMenu_loadConfiguration.triggered.connect(self.on_file_load_cfg)

        # help menu
        self.ui.PB_helpMenu_about.triggered.connect(self.on_help_about)
        self.ui.PB_helpMenu_docs.triggered.connect(self.on_help_docs)
        self.ui.PB_helpMenu_openLogFile.triggered.connect(self.on_open_log)

        # SERIAL PORT setup
        self.ui.PB_serialSetup.clicked.connect(self.set_serial_settings_with_dialog)
        self.ui.PB_refreshCommPortsList.clicked.connect(self.refresh_ports_list)
        self.ui.PB_commPortCtrl.clicked.connect(self.on_port_hdlr_button)

        # data note data send and button fields
        for idx, data_field in enumerate(self.ui_data_fields):
            data_field.textChanged.connect(partial(self.on_data_field_change, idx))

        for idx, data_send_pb in enumerate(self.ui_data_send_buttons):
            data_send_pb.clicked.connect(partial(self.on_send_data_button, idx))

        self.ui.PB_clearLog.clicked.connect(self.clear_log_window)
        self.ui.PB_exportLog.clicked.connect(self.save_log_window)
        self.ui.PB_exportRxTxData.clicked.connect(self.save_rx_tx_data)
        self.ui.CB_rxToLog.clicked.connect(self.on_rx_display_mode_change)
        self.ui.CB_txToLog.clicked.connect(self.on_tx_display_mode_change)
        self.ui.RB_GROUP_outputRepresentation.buttonClicked.connect(self.on_out_representation_mode_change)
        self.ui.CB_rxNewLine.clicked.connect(self.on_rx_new_line_change)
        self.ui.SB_rxTimeoutMs.valueChanged.connect(self.on_rx_new_line_timeout_change)

    def connect_app_signals_to_slots(self) -> None:
        self.sig_write.connect(self.log_text)
        self.sig_warning.connect(self.log_text)
        self.sig_error.connect(self.log_text)

        self.sig_close.connect(self.on_quit_app_event)

        self.port_hdlr.sig_connection_successful.connect(self.on_connect_event)
        self.port_hdlr.sig_connection_closed.connect(self.on_disconnect_event)
        self.port_hdlr.sig_data_received.connect(self.on_data_received_event)
        self.port_hdlr.sig_data_received1.connect(self.on_data_received_event1)


    def connect_update_signals_to_slots(self) -> None:
        self.data_cache.sig_serial_settings_update.connect(self.on_serial_settings_update)
        self.data_cache.sig_data_field_update.connect(self.on_data_field_update)
        self.data_cache.sig_rx_display_update.connect(self.on_rx_display_mode_update)
        self.data_cache.sig_tx_display_update.connect(self.on_tx_display_mode_update)
        self.data_cache.sig_out_representation_update.connect(self.on_out_representation_mode_update)
        self.data_cache.sig_new_line_on_rx_update.connect(self.on_rx_new_line_update)

    def init_gui(self) -> None:
        """Init GUI and emit signals to update/check fields"""

        # update current window name with version string
        self.set_main_window_name()

        self._set_mru_cfg_paths()

        # serial port settings
        baudrate_validator = QtGui.QIntValidator(0, serialutil.SerialBase.BAUDRATES[-1])
        print(baudrate_validator)
        self.ui.DD_baudrate.setValidator(baudrate_validator)
        self.ui.DD_baudrate.addItems([str(baudrate) for baudrate in serialutil.SerialBase.BAUDRATES])
        baudrate_idx = self.ui.DD_baudrate.findText(str(base.DEFAULT_BAUDRATE))
        print(baudrate_idx)
        self.ui.DD_baudrate.setCurrentIndex(baudrate_idx)

        if self.args.load_mru_cfg:
            mru_path = paths.get_most_recently_used_cfg_file()
            if mru_path is not None:
                self.cfg_hdlr.load_cfg(mru_path)
            else:
                self.log_text(
                    "`--load-cfg` argument is set, but there is no most recently used configuration path available.",
                    colors.LOG_WARNING,
                )
        else:
            self.cfg_hdlr.set_default_cfg()

        self.clear_log_window()

        logging.info("GUI initialized.")

    def _set_mru_cfg_paths(self) -> None:
        """Set most recently used configurations to "File menu > Recently used configurations" list"""
        self.ui.PB_fileMenu_recentlyUsedConfigurations.clear()

        files = paths.get_recently_used_cfgs(ui_defs.NUM_OF_MAX_RECENTLY_USED_CFG_GUI)
        for file_path in files:
            name = os.path.basename(file_path)

            action = QtWidgets.QAction(name, self)
            action.triggered.connect(partial(self.on_file_load_cfg, file_path))
            self.ui.PB_fileMenu_recentlyUsedConfigurations.addAction(action)

    def set_main_window_name(self, name: Optional[str] = None) -> None:
        """Set additional name to the main application GUI window."""
        main_name = f"{ui_defs.APP_NAME} v{serial_tool.__version__}"
        if name:
            main_name += f" - {name}"

        self.setWindowTitle(main_name)

    def get_selected_port(self) -> str:
        """Return name of currently selected serial port from a drop down menu."""
        return self.ui.DD_commPortSelector.currentText()

    def get_selected_baudrate(self) -> str:
        """Return selected/set baudrate from a drop down menu."""
        return self.ui.DD_baudrate.currentText()

    def set_data_button_state(self, ch_idx: int, is_enabled: bool) -> None:
        """Set chosen data data channel push button state to enabled/disabled."""
        print(is_enabled)
        self.ui_data_send_buttons[ch_idx].setEnabled(is_enabled)

    def set_data_buttons_state(self, is_enabled: bool) -> None:
        """Set all data send push button state to enabled/disabled."""
        for button in self.ui_data_send_buttons:
            button.setEnabled(is_enabled)

    def set_new_button_state(self, ch_idx: int, is_enabled: bool) -> None:
        """Set chosen sequence data channel push button state to enabled/disabled."""
        self.ui_seq_send_buttons[ch_idx].setEnabled(is_enabled)

    def set_new_buttons_state(self, is_enabled: bool) -> None:
        """Set all sequence send push button state to enabled/disabled."""
        for button in self.ui_seq_send_buttons:
            button.setEnabled(is_enabled)

    def stop_all_seq_tx_threads(self) -> None:
        """Stop all sequence threads, ignoring all exceptions."""
        for idx, seq_worker in enumerate(self._seq_tx_workers):
            try:
                if seq_worker is not None:
                    seq_worker.sig_seq_stop_request.emit()
            except Exception as err:
                logging.error(f"Unable to stop sequence {idx + 1} thread.\n{err}")

    def colorize_text_field(self, field: QtWidgets.QLineEdit, status: models.TextFieldStatus) -> None:
        """Colorize given text input field with pre-defined scheme (see status parameter)."""
        color = models.TextFieldStatus.get_color(status)
        field.setStyleSheet(f"{ui_defs.DEFAULT_FONT_STYLE} background-color: {color}")

    def set_connection_buttons_state(self, is_enabled: bool) -> None:
        """
        Set comm port connection status button state (text and color).

        Args:
            is_enabled:
                - if True: text = CONNECTED, color = green
                - if False: text = not connected, color = red
        """
        if is_enabled:
            self.ui.PB_commPortCtrl.setText(ui_defs.COMM_PORT_CONNECTED_TEXT)
            self.ui.PB_commPortCtrl.setStyleSheet(
                f"{ui_defs.DEFAULT_FONT_STYLE} background-color: {colors.COMM_PORT_CONNECTED}"
            )
        else:
            self.ui.PB_commPortCtrl.setText(ui_defs.COMM_PORT_NOT_CONNECTED_TEXT)
            self.ui.PB_commPortCtrl.setStyleSheet(
                f"{ui_defs.DEFAULT_FONT_STYLE} background-color: {colors.COMM_PORT_NOT_CONNECTED}"
            )

    def get_rx_new_line_timeout_msec(self) -> int:
        """Return value from RX new line spinbox timeout setting."""
        return int(self.ui.SB_rxTimeoutMs.value() // 1e3)  # (to ms conversion)

    @QtCore.pyqtSlot(str, str)
    def log_text(
            self, msg: str, color: str = colors.LOG_NORMAL, append_new_line: bool = True, ensure_new_line: bool = True
    ) -> None:
        """
        Write to log window with a given color.

        Args:
            msg: message to write to log window.
            color: color of displayed text (hex format).
            append_new_line: if True, new line terminator is appended to a message
            ensure_new_line: if True, additional cursor position check is implemented
                so given msg is really displayed in new line.
        """
        self._display_rx_data = True
        print("message: ", msg)
        print(type(msg))
        msg.replace("0x0a;", "\n")
        print("After Remove 0x0a message: ", msg)
        if append_new_line:
            msg = f"{msg}\n"

        if ensure_new_line:
            if self.ui.TE_log.textCursor().position() != 0:
                msg = f"\n{msg}"

        # if autoscroll is not in use, set previous location.
        current_vertical_scrollbar_pos = self.ui.TE_log.verticalScrollBar().value()
        # always insert at the end of the log window
        self.ui.TE_log.moveCursor(QtGui.QTextCursor.End)

        self.ui.TE_log.setTextColor(QtGui.QColor(color))
        self.ui.TE_log.insertPlainText(msg)
        self.ui.TE_log.setTextColor(QtGui.QColor(colors.LOG_NORMAL))

        if self.ui.PB_autoScroll.isChecked():
            self.ui.TE_log.moveCursor(QtGui.QTextCursor.End)
        else:
            self.ui.TE_log.verticalScrollBar().setValue(current_vertical_scrollbar_pos)

        logging.debug(f"[LOG_WINDOW]: {msg.strip()}")

    def log_html(self, msg: str) -> None:
        """
        Write HTML content to log window with a given color.
        NOTE: override autoscroll checkbox setting - always display message.

        Args:
            msg: html formatted message to write to log window.
        """
        msg = f"{msg}<br>"
        self.ui.TE_log.moveCursor(QtGui.QTextCursor.End)
        self.ui.TE_log.insertHtml(msg)

        if self.ui.PB_autoScroll.isChecked():
            self.ui.TE_log.ensureCursorVisible()

        logging.debug(f"writeHtmlToLogWindow: {msg}")

    ################################################################################################
    # Menu bar slots
    ################################################################################################
    @QtCore.pyqtSlot()
    def on_file_create_new_cfg(self) -> None:
        """
        Create new blank configuration and discard any current settings.
        User is previously asked for confirmation.
        """
        if self.confirm_action_dialog("Warning!", "Create new configuration?\nThis will discard any changes!"):
            self.data_cache.cfg_file_path = None
            self.cfg_hdlr.set_default_cfg()

            self.log_text("New default configuration created.", colors.LOG_GRAY)

            self.set_main_window_name()
        else:
            logging.debug("New configuration request canceled.")

    @QtCore.pyqtSlot()
    def on_file_save_cfg(self) -> None:
        """
        Save current configuration to a file. File path is selected with default os GUI pop-up.
        """
        logging.info("Inside file Save config.")
        if self.data_cache.cfg_file_path is None:
            cfg_file_path = os.path.join(paths.get_default_log_dir(), base.DEFAULT_CFG_FILE_NAME)
        else:
            cfg_file_path = self.data_cache.cfg_file_path

        path = self.ask_for_save_file_path("Save configuration...", cfg_file_path, base.CFG_FILE_EXT_FILTER)
        if path is None:
            logging.debug("Save configuration request canceled.")
        else:
            self.data_cache.cfg_file_path = path
            self.cfg_hdlr.save_cfg(path)

            paths.add_cfg_to_recently_used_cfgs(path)
            self._set_mru_cfg_paths()

            self.log_text(f"Configuration saved: {path}", colors.LOG_GRAY)
            self.set_main_window_name(path)

    @QtCore.pyqtSlot()
    def on_file_load_cfg(self, path: Optional[str] = None) -> None:
        """
        Load configuration from a file and discard any current settings.
        User is previously asked for confirmation.

        Args:
            path: if None, user is asked to entry file path.
        """
        refresh_menu = False

        if path is None:
            if self.data_cache.cfg_file_path is None:
                cfg_dir = paths.get_default_log_dir()
            else:
                cfg_dir = os.path.dirname(self.data_cache.cfg_file_path)

            if self.confirm_action_dialog("Warning!", "Loading new configuration?\nThis will discard any changes!"):
                path = self.ask_for_open_file_path("Load configuration...", cfg_dir, base.CFG_FILE_EXT_FILTER)
                if path is not None:
                    self.data_cache.cfg_file_path = path
                    self.cfg_hdlr.load_cfg(path)
                    refresh_menu = True
                else:
                    logging.debug("Load configuration request canceled.")
        else:
            path = os.path.normpath(path)
            self.cfg_hdlr.load_cfg(path)
            self.data_cache.cfg_file_path = path
            refresh_menu = True

        if refresh_menu:
            assert path is not None
            paths.add_cfg_to_recently_used_cfgs(path)
            self._set_mru_cfg_paths()

            self.log_text(f"Configuration loaded: {path}", colors.LOG_GRAY)
            self.set_main_window_name(path)

    @QtCore.pyqtSlot()
    def on_help_about(self) -> None:
        """Print current version and info links to log window."""
        lines = []
        lines.append(f"<br>************ Serial Tool v{serial_tool.__version__} ************")
        # add extra new line
        lines.append(f'Domen Jurkovic @ <a href="{base.LINK_DAMGORANLABS}">Damogran Labs</a><br>')
        lines.append(f'Repository: <a href="{base.LINK_REPOSITORY}">{base.LINK_REPOSITORY}</a>')
        lines.append(f'Docs: <a href="{base.LINK_DOCS}">{base.LINK_DOCS}</a>')
        lines.append(f'Homepage: <a href="{base.LINK_HOMEPAGE}">{base.LINK_HOMEPAGE}</a>')

        self.log_html("<br>".join(lines))

    @QtCore.pyqtSlot()
    def on_help_docs(self) -> None:
        """Open Github README page in a web browser."""
        webbrowser.open(base.LINK_DOCS, new=2)  # new=2 new tab

        logging.debug("Online docs opened.")

    @QtCore.pyqtSlot()
    def on_open_log(self) -> None:
        """Open Serial Tool log file."""
        path = paths.get_log_file_path()

        webbrowser.open(f"file://{path}", new=2)



    ################################################################################################
    # serial settings slots
    ################################################################################################
    @QtCore.pyqtSlot()
    def set_serial_settings_with_dialog(self) -> None:
        """Open serial settings dialog and set new port settings."""
        dialog = setup_dialog.SerialSetupDialog(self.data_cache.serial_settings)
        dialog.setWindowModality(QtCore.Qt.ApplicationModal)
        dialog.display()
        dialog.exec_()

        if dialog.must_apply_settings():
            self.data_cache.serial_settings = dialog.get_settings()

            self.refresh_ports_list()

            self.log_text(f"New serial settings applied: {self.data_cache.serial_settings}", colors.LOG_GRAY)
        else:
            logging.debug("New serial settings request canceled.")

    @QtCore.pyqtSlot()
    def on_serial_settings_update(self) -> None:
        """Load new serial settings dialog values from data model."""
        self.refresh_ports_list()  # also de-init

        if self.data_cache.serial_settings.port is not None:
            port = self.ui.DD_commPortSelector.findText(self.data_cache.serial_settings.port)
            if port == -1:
                self.log_text(
                    f"No {self.data_cache.serial_settings.port} serial port currently available.",
                    colors.LOG_WARNING,
                )
            else:
                self.ui.DD_commPortSelector.setCurrentIndex(port)

        baudrate = self.ui.DD_baudrate.findText(str(self.data_cache.serial_settings.baudrate))
        if baudrate == -1:
            self.log_text(
                f"No {self.data_cache.serial_settings.baudrate} baudrate available, manually added.",
                colors.LOG_WARNING,
            )
            self.ui.DD_baudrate.addItem(str(self.data_cache.serial_settings.baudrate))
            self.ui.DD_baudrate.setCurrentText(str(self.data_cache.serial_settings.baudrate))
        else:
            self.ui.DD_baudrate.setCurrentIndex(baudrate)

        logging.debug("New serial settings applied.")

    @QtCore.pyqtSlot()
    def refresh_ports_list(self) -> None:
        """Refresh list of available serial port list. Will close current port."""
        logging.debug("Serial port list refresh request.")

        self.port_hdlr.deinit_port()

        ports = serial_hdlr.SerialPort().get_available_ports()
        self.ui.DD_commPortSelector.clear()
        self.ui.DD_commPortSelector.addItems(list(sorted(ports, reverse=True)))

    @QtCore.pyqtSlot()
    def on_port_hdlr_button(self) -> None:
        """Connect/disconnect from a port with serial settings."""
        if self.ui.PB_commPortCtrl.text() == ui_defs.COMM_PORT_CONNECTED_TEXT:
            # currently connected, stop all sequences and disconnect
            self.stop_all_seq_tx_threads()  # might be a problem with unfinished, blockin sequences

            self.port_hdlr.deinit_port()
            self.log_text("Disconnect request.", colors.LOG_GRAY)
        else:
            # currently disconnected, connect
            serial_port = self.get_selected_port()
            if not serial_port:
                raise RuntimeError("No available port to init serial communication.")
            self.data_cache.serial_settings.port = serial_port

            baudrate = self.get_selected_baudrate()
            if not baudrate:
                raise RuntimeError("Set baudrate of serial port.")
            self.data_cache.serial_settings.baudrate = int(baudrate)
            print(baudrate)

            self.port_hdlr.serial_settings = self.data_cache.serial_settings
            print("Before Opening Rx Read Thread\n", self.port_hdlr.serial_settings)
            self.port_hdlr.init_port_and_rx_thread()

            self.log_text("Connect request.", colors.LOG_GRAY)

    ################################################################################################
    # application generated events
    ################################################################################################
    @QtCore.pyqtSlot()
    def on_connect_event(self) -> None:
        """This function is called once connection to port is successfully created."""
        self.set_connection_buttons_state(True)
        self.ui.DD_commPortSelector.setEnabled(False)
        self.ui.DD_baudrate.setEnabled(False)


    @QtCore.pyqtSlot()
    def on_disconnect_event(self) -> None:
        """This function is called once connection to port is closed."""
        self.set_connection_buttons_state(False)
        self.ui.DD_commPortSelector.setEnabled(True)
        self.ui.DD_baudrate.setEnabled(True)


        logging.debug("\tEvent: disconnect")

    #set all the CAN configuration which argument of list
    @QtCore.pyqtSlot(list)
    def on_data_received_event1(self, data: List[int]) -> None:

        db = cantools.database.load_file('bmscanincfg.dbc')
        msg_1 = db.get_message_by_name('Configuration1')
        msg_2 = db.get_message_by_name('Configuration2')
        msg_3 = db.get_message_by_name('Configuration3')
        msg_4 = db.get_message_by_name('Configuration4')
        msg_5 = db.get_message_by_name('Configuration5')
        msg_6 = db.get_message_by_name('Configuration6')
        msg_7 = db.get_message_by_name('Configuration7')
        msg_8 = db.get_message_by_name('Configuration8')

        for ch_idx, field in enumerate(self.data_cache.parsed_data_fields):#collecting value from the parsed_data_fields to field list variable
            if (field is not None):
                if (ch_idx == 0):
                    noofcell = field
                if (ch_idx == 1):
                    noofcellinparallel = field
                if (ch_idx == 2):
                    noofslaves = field
                if (ch_idx == 3):
                    conductorcutofftime = field
                if (ch_idx == 4):
                    conductorontimer = field
                if (ch_idx == 5):
                    ratedcellcapacity = field
                if (ch_idx == 6):
                    cellUVcutOFF = field
                if (ch_idx == 7):
                    cellUVrecovery = field
                if (ch_idx == 8):
                    cellOVcutoff = field
                if (ch_idx == 9):
                    cellOVrecovery = field
                if (ch_idx == 10):
                    packuvcutoff = field
                if (ch_idx == 11):
                    packuvrecovery = field
                if (ch_idx == 12):
                    packovcutoff = field
                if (ch_idx == 13):
                    packOVrecovery = field
                if (ch_idx == 14):
                    Chargingcurrentcutoff = field
                if (ch_idx == 15):
                    Chargingcurrentrecovery = field
                if (ch_idx == 16):
                    Chargingovertemperaturecutoff = field
                if (ch_idx == 17):
                    ChargingOvertemperaturerecovery = field
                if (ch_idx == 18):
                    Dischargingcurrentcutoff = field[0]#changing the list variable into into variable
                if (ch_idx == 19):
                    Dischragingcurrentrecovery = field[0]
                if (ch_idx == 20):
                    ChargingunderTemperaturecutoff = field[0]
                if (ch_idx == 21):
                    ChargingunderTemperaturerecovery = field[0]
                if (ch_idx == 22):
                    Dischargingovertemperaturecutoff = field
                if (ch_idx == 23):
                    Dischargingovertemperaturerecovery = field
                if (ch_idx == 24):
                    DischargingUndertemperaturecutoff = field
                if (ch_idx == 25):
                    Dischargingundertemperaturerecovery = field[0]
                if (ch_idx == 26):
                    StartCellbalancingvoltage = field
                if (ch_idx == 27):
                    Balancingdeltadifference = field
                if (ch_idx == 28):
                    AHChargedischarge = field
                if (ch_idx == 29):
                    RatedCellcapacity = field
                if (ch_idx == 30):
                    ShortCirCurrent = field[0]

        #can configuration ID
        msgID_1 = bytearray(msg_1.frame_id.to_bytes(4, 'big'))
        msgID_2 = bytearray(msg_2.frame_id.to_bytes(4, 'big'))
        msgID_3 = bytearray(msg_3.frame_id.to_bytes(4, 'big'))
        msgID_4 = bytearray(msg_4.frame_id.to_bytes(4, 'big'))
        msgID_5 = bytearray(msg_5.frame_id.to_bytes(4, 'big'))
        msgID_6 = bytearray(msg_6.frame_id.to_bytes(4, 'big'))
        msgID_7 = bytearray(msg_7.frame_id.to_bytes(4, 'big'))
        msgID_8 = bytearray(msg_8.frame_id.to_bytes(4, 'big'))

        #can configuration msg lenght
        msgID_1.append(0x8)
        msgID_2.append(0x8)
        msgID_3.append(0x8)
        msgID_4.append(0x8)
        msgID_5.append(0x8)
        msgID_6.append(0x8)
        msgID_7.append(0x8)
        msgID_8.append(0x8)

        #configuration 1
        data1 = msg_1.encode({'No__Of_Cells': noofcell[0], 'No__Of_Cells_in_Parallel': noofcellinparallel[0],
                              'No__Of_Slaves': noofslaves[0], 'Contactor_Cut_Off_Time': conductorcutofftime[0],
                              'Contactor_ON_Timer': conductorontimer[0], 'Rated_Cell_Capacity': ratedcellcapacity[0]})
        # configuration 2
        data2 = msg_2.encode({'Cell_Under_voltage_cutoff': cellUVcutOFF[0], 'Cell_Under_voltage_recovery': cellUVrecovery[0],
                               'Cell_Over_voltage_cutoff': cellOVcutoff[0], 'Cell_Over_voltage_recovery': cellOVrecovery[0]})
        # configuration 3
        data3 = msg_3.encode({'Pack_UV_cutoff': packuvcutoff[0], 'Pack_UV_recovery': packuvrecovery[0],
                              'Pack_OV_cutoff': packovcutoff[0], 'Pack_OV_recovery': packOVrecovery[0]})
        # configuration 4
        data4 = msg_4.encode({'Charging_current_cutoff': Chargingcurrentcutoff[0],
                              'Charging_current_recovery': Chargingcurrentrecovery[0],
                              'Charging_over_temperature_cutoff': Chargingovertemperaturecutoff[0],
                              'Charging_Over_temperature_recovery': ChargingOvertemperaturerecovery[0]})


        # Dischargingcurrentcutoff packing
        pack_Dischargingcurrentcutoff = struct.pack('>L',Dischargingcurrentcutoff )  # Packing an unsigned long number.
        Dischargingcurrentcutoff = struct.unpack('>l', pack_Dischargingcurrentcutoff)[0]  # Unpacking a packed unsigned long number to long (revert action).
        print("DischargingCurrent=" , Dischargingcurrentcutoff)

        #Dischragingcurrentrecovery packing
        pack_Dischragingcurrentrecovery = struct.pack('>L',Dischragingcurrentrecovery)  # Packing an unsigned long number.
        Dischragingcurrentrecovery= struct.unpack('>l', pack_Dischragingcurrentrecovery)[0]  # Unpacking a packed unsigned long number to long (revert action).
        print("Dischragingcurrentrecovery=" ,Dischragingcurrentrecovery)

        # ChargingunderTemperaturecutoff packing
        pack_ChargingunderTemperaturecutoff=struct.pack('>L',ChargingunderTemperaturecutoff)
        ChargingunderTemperaturecutoff= struct.unpack('>l',pack_ChargingunderTemperaturecutoff )[0]
        print("pack_ChargingunderTemperaturecutoff=",ChargingunderTemperaturecutoff )

        #ChargingunderTemperaturerecovery packing
        pack_ChargingunderTemperaturerecovery = struct.pack('>L', ChargingunderTemperaturerecovery)
        ChargingunderTemperaturerecovery= struct.unpack('>l', pack_ChargingunderTemperaturerecovery)[0]
        print("pack_ChargingunderTemperaturerecovery=", ChargingunderTemperaturerecovery)

        #Dischargingundertemperaturerecovery packing
        pack_Dischargingundertemperaturerecovery = struct.pack('>L',Dischargingundertemperaturerecovery)
        Dischargingundertemperaturerecovery= struct.unpack('>l', pack_Dischargingundertemperaturerecovery)[0]
        print("pack_Dischargingundertemperaturerecovery=",Dischargingundertemperaturerecovery )

        #ShortCirCurrent packing
        pack_ShortCirCurrent = struct.pack('>L', ShortCirCurrent)
        ShortCirCurrent = struct.unpack('>l',pack_ShortCirCurrent )[0]
        print("pack_ShortCirCurrent=", ShortCirCurrent)

        # configuration 5
        data5 = msg_5.encode({'Discharging_current_cutoff': Dischargingcurrentcutoff,
                              'Dischraging_current_recovery': Dischragingcurrentrecovery,
                              'Charging_under_Temperature_cutoff': ChargingunderTemperaturecutoff,
                              'Charging_under_Temperature_recovery': ChargingunderTemperaturerecovery})
        print ("data5=",data5)

        # configuration 6
        data6 = msg_6.encode({'Discharging_over_temperature_cutoff': Dischargingovertemperaturecutoff[0],
                              'Discharging_over_temperature_recovery': Dischargingovertemperaturerecovery[0],
                              'Discharging_Under_temperature_cutoff': DischargingUndertemperaturecutoff[0],
                              'Discharging_under_temperature_recovery': Dischargingundertemperaturerecovery})
        # configuration 7
        data7 = msg_7.encode({'Start_Cell_balancing_voltage_': StartCellbalancingvoltage[0],
                              'Balancing_delta_difference': Balancingdeltadifference[0],
                              'AH_Charge_discharge': AHChargedischarge[0], 'Rated_Cell_capacity': RatedCellcapacity[0]})
        # configuration 8
        data8 =msg_8.encode({'ShortCircuitCurrent': ShortCirCurrent})


        #configuration 1
        if (Gui.canID == '0x309'):
            data=list(msgID_1) + list(data1)
            self.port_hdlr.sig_write.emit(data)
        if(Gui.canID=='0x201'):
            data = list(msgID_1) + list(data1)
            self.port_hdlr.sig_write.emit(data)
            if Gui.conf_1 == 20:
                # create and display message box
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Information)
                msg_box.setText("No__Of_Cells\nNo__Of_Cells_in_Parallel\nNo__Of_Slaves\nContactor_Cut_Off_Time\nContactor_ON_Timer\nRated_Cell_Capacity")
                msg_box.setWindowTitle("  ERROR! ")
                Gui.conf_1 += 1
                msg_box.exec_()
                quit()
            print("Gui.conf_1=",Gui.conf_1)
            Gui.conf_1 += 1

        # configuration 2
        elif (Gui.canID == '0x301'):
             data = list(msgID_2) + list(data2)
             self.port_hdlr.sig_write.emit(data)
        if(Gui.canID=='0x202'):
            data = list(msgID_2) + list(data2)
            self.port_hdlr.sig_write.emit(data)
            if (Gui.conf_2 == 20):
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Information)
                msg_box.setText("Cell_Under_voltage_cutoff\nCell_Under_voltage_recovery\nCell_Over_voltage_cutoff\nCell_Over_voltage_recovery\n")
                msg_box.setWindowTitle("  ERROR! ")
                Gui.conf_2 += 1
                msg_box.exec_()
                quit()
            Gui.conf_2 += 1

        # configuration 3
        elif (Gui.canID == '0x302'):
            data=list(msgID_3) + list(data3)
            self.port_hdlr.sig_write.emit(data)

        if(Gui.canID=='0x203'):
            data=list(msgID_3) + list(data3)
            self.port_hdlr.sig_write.emit(data)
            if (Gui.conf_3 == 20):
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Information)
                msg_box.setText("Pack_UV_cutoff\nPack_UV_recovery\nPack_OV_cutoff\nPack_OV_recovery\n")
                msg_box.setWindowTitle("  ERROR! ")
                Gui.conf_3 += 1
                msg_box.exec_()
                quit()
            Gui.conf_3 += 1

        # configuration 4
        elif (Gui.canID == '0x303'):
            data=list(msgID_4) + list(data4)
            self.port_hdlr.sig_write.emit(data)

        if(Gui.canID=='0x204'):
            data=list(msgID_4) + list(data4)
            self.port_hdlr.sig_write.emit(data)
            if (Gui.conf_4 == 20):
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Information)
                msg_box.setText("Charging_current_cutoff\nCharging_current_recovery\nCharging_over_temperature_cutoff\nCharging_Over_temperature_recovery\n")
                msg_box.setWindowTitle("  ERROR! ")
                Gui.conf_4 += 1
                msg_box.exec_()
                quit()
            Gui.conf_4 += 1
        # configuration 5
        elif (Gui.canID == '0x304'):
            data=list(msgID_5) + list(data5)
            self.port_hdlr.sig_write.emit(data)
        if (Gui.canID == '0x205'):
            data=list(msgID_5) + list(data5)
            self.port_hdlr.sig_write.emit(data)
            if (Gui.conf_5 == 20):
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Information)
                msg_box.setText("Discharging_current_cutoff\nDischraging_current_recovery\nCharging_under_Temperature_cutoff\nCharging_under_Temperature_recovery\n")
                msg_box.setWindowTitle("  ERROR! ")
                Gui.conf_5 += 1
                msg_box.exec_()
                quit()
            Gui.conf_5 += 1

        # configuration 6
        elif (Gui.canID == '0x305'):
            data=list(msgID_6) + list(data6)
            self.port_hdlr.sig_write.emit(data)

        if(Gui.canID == '0x206'):
            data=list(msgID_6) + list(data6)
            self.port_hdlr.sig_write.emit(data)
            if (Gui.conf_6 == 20):
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Information)
                msg_box.setText("Discharging_over_temperature_cutoff!\nDischarging_over_temperature_recovery!\nDischarging_Under_temperature_cutoff!\n,Discharging_under_temperature_recovery!\n")
                msg_box.setWindowTitle("  ERROR! ")
                Gui.conf_6 += 1
                msg_box.exec_()
                quit()
            Gui.conf_6 += 1

        # configuration 7
        elif (Gui.canID == '0x306'):
            data=list(msgID_7) + list(data7)
            self.port_hdlr.sig_write.emit(data)

        if (Gui.canID == '0x207'):
            data=list(msgID_7) + list(data7)
            self.port_hdlr.sig_write.emit(data)
            if (Gui.conf_7 == 20):
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Information)
                msg_box.setText("Start_Cell_balancing_voltage!\nBalancing_delta_difference!\nAH_Charge_discharge!\nRated_Cell_capacity!\n")
                msg_box.setWindowTitle("  ERROR! ")
                Gui.conf_7 += 1
                msg_box.exec_()
                quit()
            Gui.conf_7 += 1

        # configuration 8
        elif (Gui.canID == '0x307'):
            data = list(msgID_8) + list(data8)
            data.append(0)
            data.append(0)
            data.append(0)
            data.append(0)
            data.append(0)
            data.append(0)
            self.port_hdlr.sig_write.emit(data)
        if (Gui.canID == '0x208'):
            self.port_hdlr.sig_write.emit(data)
            if (Gui.conf_8 == 20):
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Information)
                msg_box.setText("ShortCircuitCurrent!\n")
                msg_box.setWindowTitle("  ERROR! ")
                Gui.conf_8 += 1
                msg_box.exec_()
                quit()
            Gui.conf_8 += 1

        data_str = self._convert_data(data, self.data_cache.output_data_representation, ui_defs.RX_DATA_SEPARATOR)
        print("RX data=" + data_str)
        self.data_cache.all_rx_tx_data.append(f"{ui_defs.EXPORT_RX_TAG}{data}")
        if self.data_cache.display_rx_data:
            msg = f"{data_str}"
            if self.data_cache.new_line_on_rx:
                # insert \n on RX data, after specified timeout
                if self._display_rx_data:
                    # we are in the middle of displaying RX data, check timestamp delta
                    if (time.time() - self._last_rx_event_timestamp) > self.get_rx_new_line_timeout_msec():
                        msg = f"\n{data_str}"
                # else: # not enough time has passed, just add data without new line
            # else: # some RX data or other message was displayed in log window since last RX data display
            # else: # no RX on new line is needed, just add RX data
            self.log_text(msg, colors.TX_DATA, False, False)
            self._display_rx_data = True

        self._last_rx_event_timestamp = time.time()

        logging.debug(f"\tEvent: data received: {data_str}")

    @QtCore.pyqtSlot(list)
    def on_data_received_event(self, data: List[int]) -> None:
        """This function is called once data is received on a serial port."""

        lenght=len(data)
        if(lenght>17):#check the data lenght
            Gui.canID=hex(((data[17] << 24) | data[18] << 16) | ((data[19] << 8) | data[20]))#combine the canID from list of data
        else:
            Gui.canID = hex(((data[0] << 24) | data[1] << 16) | ((data[2] << 8) | data[3]))#combine the canID from list of data



        data_str = self._convert_data(data, self.data_cache.output_data_representation, ui_defs.RX_DATA_SEPARATOR)
        print("RX data" + data_str)
        self.data_cache.all_rx_tx_data.append(f"{ui_defs.EXPORT_RX_TAG}{data}")
        msg = f"{data_str}\n"
        if self.data_cache.display_rx_data:
            msg = f"{data_str}"
            if self.data_cache.new_line_on_rx:
                # insert \n on RX data, after specified timeout
                if self._display_rx_data:
                    # we are in the middle of displaying RX data, check timestamp delta
                    if (time.time() - self._last_rx_event_timestamp) > self.get_rx_new_line_timeout_msec():
                        msg = f"\n{data_str}"


        self.log_text(msg, colors.LOG_RX_DATA, False, False)
        self._display_rx_data = True

        self._last_rx_event_timestamp = time.time()
        logging.debug(f"\tEvent: data received: {data_str}")

    @QtCore.pyqtSlot(int)
    def on_seq_finish_event(self, seq_idx: int) -> None:
        """This function is called once sequence sending thread is finished."""
        self.ui_seq_send_buttons[seq_idx].setText(ui_defs.SEQ_BUTTON_IDLE_TEXT)
        self.ui_seq_send_buttons[seq_idx].setStyleSheet(f"{ui_defs.DEFAULT_FONT_STYLE} background-color: None")
        self._seq_threads[seq_idx] = None

        logging.debug(f"\tEvent: sequence {seq_idx + 1} finished")

    @QtCore.pyqtSlot(int, int)
    def on_seq_send_event(self, seq_idx: int, ch_idx: int) -> None:
        """This function is called once data is send from send sequence thread."""
        data = self.data_cache.parsed_data_fields[ch_idx]
        assert data is not None
        data_str = self._convert_data(data, self.data_cache.output_data_representation, ui_defs.TX_DATA_SEPARATOR)

        self.data_cache.all_rx_tx_data.append(
            f"{ui_defs.SEQ_TAG}{seq_idx + 1}_CH{ch_idx + 1}{ui_defs.EXPORT_TX_TAG}{data}")
        if self.data_cache.display_tx_data:
            msg = f"{ui_defs.SEQ_TAG}{seq_idx + 1}_CH{ch_idx + 1}: {data_str}"

            self.log_text(msg, colors.LOG_TX_DATA)

        logging.debug(f"\tEvent: sequence {seq_idx + 1}, data channel {ch_idx + 1} send request")

    @QtCore.pyqtSlot(int)
    def stop_seq_request_event(self, ch_idx: int) -> None:
        """Display "stop" request sequence action."""
        worker = self._seq_tx_workers[ch_idx]
        assert worker is not None
        worker.sig_seq_stop_request.emit()

        logging.debug(f"\tEvent: sequence {ch_idx + 1} stop request")

    @QtCore.pyqtSlot()
    def on_quit_app_event(self) -> None:
        """Deinit serial port, close GUI."""
        self.port_hdlr.deinit_port()

        self.close()

    ################################################################################################
    # data/sequence fields/buttons slots
    ################################################################################################
    @QtCore.pyqtSlot(int)
    def on_data_field_update(self, ch_idx: int) -> None:
        """Actions to take place once data field is updated (for example, from load configuration)."""
        self.ui_data_fields[ch_idx].setText(self.data_cache.data_fields[ch_idx])
        self.on_data_field_change(ch_idx)

    @QtCore.pyqtSlot(int)
    def on_data_field_change(self, ch_idx: int) -> None:
        """Actions to take place once any data field is changed."""
        self.data_cache.data_fields[ch_idx] = self.ui_data_fields[ch_idx].text()

        result = self._parse_data_field(ch_idx)
        print("result :")
        print(ch_idx)
        print("\n")
        self.colorize_text_field(self.ui_data_fields[ch_idx], result.status)

        if result.status == models.TextFieldStatus.OK:
            print("on_data_field_change idx: " + str(ch_idx))
            self.data_cache.parsed_data_fields[ch_idx] = result.data
            if self.port_hdlr.is_connected():
                self.set_data_button_state(0, True)
            else:
                self.set_data_button_state(0, False)
        else:  # False or None (empty field)
            self.data_cache.parsed_data_fields[ch_idx] = None
            self.set_data_button_state(0, False)

    @QtCore.pyqtSlot(int)
    def on_send_data_button(self, ch_idx: int) -> None:
        """Send data on a selected data channel."""

        db = cantools.database.load_file('BMSCANInpCnf.dbc')
        msg_9 = db.get_message_by_name('Configuration_9')
        data = bytearray(msg_9.frame_id.to_bytes(4, 'big'))
        data.append(0x8)
        data.append(0x1)
        data.append(0x1)
        data.append(0x1)
        data.append(0x1)
        data.append(0x1)
        data.append(0x1)
        data.append(0x1)
        data.append(0x1)

        self.port_hdlr.sig_write.emit(list(data))


        assert data is not None
        data_str = self._convert_data(data, self.data_cache.output_data_representation, ui_defs.TX_DATA_SEPARATOR)

        self.data_cache.all_rx_tx_data.append(f"CH{ch_idx}{ui_defs.EXPORT_TX_TAG}{data}")
        if self.data_cache.display_tx_data:
            self.log_text(data_str, colors.LOG_TX_DATA)


    ################################################################################################
    # log settings slots
    ################################################################################################
    @QtCore.pyqtSlot()
    def clear_log_window(self) -> None:
        self.data_cache.all_rx_tx_data = []
        self.ui.TE_log.clear()

    @QtCore.pyqtSlot()
    def save_log_window(self) -> None:
        """
        Save (export) content of a current log window to a file.
        Pick destination with default OS pop-up window.
        """
        default_path = os.path.join(paths.get_default_log_dir(), base.DEFAULT_LOG_EXPORT_FILENAME)
        path = self.ask_for_save_file_path("Save log window content...", default_path, base.LOG_EXPORT_FILE_EXT_FILTER)
        if path is not None:
            with open(path, "w+", encoding="utf-8") as f:
                lines = self.ui.TE_log.toPlainText()
                f.writelines(lines)

            self.log_text(f"Log window content saved to: {path}", colors.LOG_GRAY)
        else:
            logging.debug("Save log window content request canceled.")

    @QtCore.pyqtSlot()
    def save_rx_tx_data(self) -> None:
        """
        Save (export) content of all RX/TX data to a file.
        Pick destination with default OS pop-up window.
        """
        default_path = os.path.join(paths.get_default_log_dir(), base.DEFAULT_DATA_EXPORT_FILENAME)
        path = self.ask_for_save_file_path("Save raw RX/TX data...", default_path, base.DATA_EXPORT_FILE_EXT_FILTER)
        if path is not None:
            with open(path, "w+", encoding="utf-8") as f:
                for data in self.data_cache.all_rx_tx_data:
                    f.write(data + "\n")

            self.data_cache.all_rx_tx_data = []
            self.log_text(f"RX/TX data exported: {path}", colors.LOG_GRAY)
        else:
            logging.debug("RX/TX data export request canceled.")

    @QtCore.pyqtSlot()
    def on_rx_display_mode_update(self) -> None:
        """
        Action to take place once RX-to-log checkbox setting is altered (for example, on load configuration).
        """
        self.ui.CB_rxToLog.setChecked(self.data_cache.display_rx_data)

    @QtCore.pyqtSlot()
    def on_rx_display_mode_change(self) -> None:
        """Get RX-to-log checkbox settings from GUI."""
        self.data_cache.display_rx_data = self.ui.CB_rxToLog.isChecked()

    @QtCore.pyqtSlot()
    def on_tx_display_mode_update(self) -> None:
        """
        Action to take place once TX-to-log checkbox setting is altered (for example, on load configuration).
        """
        self.ui.CB_txToLog.setChecked(self.data_cache.display_tx_data)

    @QtCore.pyqtSlot()
    def on_tx_display_mode_change(self) -> None:
        """Get TX-to-log checkbox settings from GUI."""
        self.data_cache.display_tx_data = self.ui.CB_txToLog.isChecked()

    @QtCore.pyqtSlot()
    def on_out_representation_mode_update(self) -> None:
        """
        Action to take place once outputDataRepresentation setting is altered (for example, on load configuration).
        """
        self.ui.RB_GROUP_outputRepresentation.button(self.data_cache.output_data_representation).click()

    @QtCore.pyqtSlot()
    def on_out_representation_mode_change(self) -> None:
        """Get output representation type from GUI selection."""
        self.data_cache.output_data_representation = models.OutputRepresentation(
            self.ui.RB_GROUP_outputRepresentation.checkedId()
        )

    @QtCore.pyqtSlot()
    def on_rx_new_line_update(self) -> None:
        """Action to take place once RX new line setting is altered (for example, on load configuration)."""
        self.ui.CB_rxNewLine.setChecked(self.data_cache.new_line_on_rx)
        if self.data_cache.new_line_on_rx:
            self.ui.SB_rxTimeoutMs.setEnabled(True)
        else:
            self.ui.SB_rxTimeoutMs.setEnabled(False)

    @QtCore.pyqtSlot()
    def on_rx_new_line_change(self) -> None:
        """Get RX new line settings of log RX/TX data."""
        self.data_cache.new_line_on_rx = self.ui.CB_rxNewLine.isChecked()
        if self.data_cache.new_line_on_rx:
            self.ui.SB_rxTimeoutMs.setEnabled(True)
        else:
            self.ui.SB_rxTimeoutMs.setEnabled(False)

    @QtCore.pyqtSlot()
    def on_rx_new_line_timeout_update(self) -> None:
        """Action to take place once RX new line timeout setting is altered (for example, on load configuration)."""
        self.ui.SB_rxTimeoutMs.setValue(self.data_cache.new_line_on_rx_timeout_msec)

    @QtCore.pyqtSlot()
    def on_rx_new_line_timeout_change(self) -> None:
        """Get RX new line settings of log RX/TX data."""
        self.data_cache.new_line_on_rx_timeout_msec = self.ui.SB_rxTimeoutMs.value()

    ################################################################################################
    # utility functions
    ################################################################################################
    def _parse_data_field(self, ch_idx: int) -> models.ChannelTextFieldParserResult:
        """Get string from a data field and return parsed data"""
        assert 0 <= ch_idx < ui_defs.NUM_OF_DATA_CHANNELS

        text = self.ui_data_fields[ch_idx].text()
        return validators.parse_channel_data(text)

    def _parse_seq_data_field(self, seq_idx: int) -> models.SequenceTextFieldParserResult:
        """Get data from a sequence field and return parsed data"""
        assert 0 <= seq_idx < ui_defs.NUM_OF_SEQ_CHANNELS
        seq = self.ui_seq_fields[seq_idx]
        text = seq.text()

        return validators.parse_seq_data(text)

    def _convert_data(self, data: List[int], new_format: models.OutputRepresentation, separator: str) -> str:
        """Convert chosen data to a string with selected format."""
        if new_format == models.OutputRepresentation.STRING:
            # Convert list of integers to a string, without data separator.
            output_data = "".join([chr(num) for num in data])
        elif new_format == models.OutputRepresentation.INT_LIST:
            # Convert list of integers to a string of integer values.
            int_data = [str(num) for num in data]
            output_data = separator.join(int_data) + separator
        elif new_format == models.OutputRepresentation.HEX_LIST:
            # Convert list of integers to a string of hex values.
            # format always as 0x** (two fields for data value)
            hex_data = [f"0x{num:02x}" for num in data]
            output_data = separator.join(hex_data) + separator
        else:
            ascii_data = [f"'{chr(num)}'" for num in data]
            output_data = separator.join(ascii_data) + separator

        return output_data.strip()

    def ask_for_save_file_path(
            self, name: str, dir_path: Optional[str] = None, filter_ext: str = "*.txt"
    ) -> Optional[str]:
        """
        Get path where file should be saved with default os GUI pop-up. Returns None on cancel or exit.
        See ask_for_file_path() for parameters.
        """
        return self.ask_for_file_path(name, True, dir_path, filter_ext)

    def ask_for_open_file_path(
            self, name: str, dir_path: Optional[str] = None, filter_ext: str = "*.txt"
    ) -> Optional[str]:
        """
        Get path where file should be saved with default os GUI pop-up. Returns None on cancel or exit.
        See ask_for_file_path() for parameters.
        """
        return self.ask_for_file_path(name, False, dir_path, filter_ext)

    def ask_for_file_path(
            self, name: str, mode: bool = True, dir_path: Optional[str] = None, filter_ext: Optional[str] = None
    ) -> Optional[str]:
        """
        Get path where file should be saved with default os GUI pop-up. Returns None on cancel or exit.

        Args:
            name: name of pop-up gui window.
            mode: if True, dialog for selecting save file is created. Otherwise, dialog to open file is created.
            dir_path: path to a folder/file where dialog should be open.
                paths.get_default_log_dir() is used by default.
            filter_ext: file extension filter (can be merged list: '"*.txt, "*.json", "*.log"')
        """
        if dir_path is None:
            dir_path = paths.get_default_log_dir()
        else:
            dir_path = os.path.normpath(dir_path)

        if filter_ext is None:
            filter_ext = ""

        if mode:
            name, _ = QtWidgets.QFileDialog.getSaveFileName(self, name, dir_path, filter_ext)
        else:
            name, _ = QtWidgets.QFileDialog.getOpenFileName(self, name, dir_path, filter_ext)

        if name == "":
            return None

        return os.path.normpath(name)

    def confirm_action_dialog(
            self,
            name: str,
            question: str,
            icon_type: Optional[QtWidgets.QMessageBox.Icon] = QtWidgets.QMessageBox.Warning,
    ) -> bool:
        """
        Pop-up system dialog with OK|Cancel options.
        Return True if user respond with click to OK button. Else, return False.
        """
        dialog = QtWidgets.QMessageBox()

        window_icon = QtGui.QIcon()
        window_icon.addPixmap(QtGui.QPixmap(":/icons/icons/SerialTool.png"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        dialog.setWindowIcon(window_icon)

        if icon_type is not None:
            dialog.setIcon(icon_type)

        dialog.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        dialog.setDefaultButton(QtWidgets.QMessageBox.Ok)
        dialog.setEscapeButton(QtWidgets.QMessageBox.Cancel)

        dialog.setText(question)
        dialog.setWindowTitle(name)

        retval = dialog.exec_()

        return retval == QtWidgets.QMessageBox.Ok

    def _app_exc_handler(self, exc_type, exc_value, traceback_obj) -> None:
        """Global function to catch unhandled exceptions."""
        msg = "\n" + " *" * 20
        msg += "\nUnhandled unexpected exception occurred! Program will try to continue with execution."
        msg += f"\n\tExc. type: {exc_type}"
        msg += f"\n\tExc. value: {exc_value}"
        msg += f"\n\tExc. traceback: {traceback.format_tb(traceback_obj)}"
        msg += "\n\n"
        logging.error(f"{msg}")

        try:
            self.sig_error.emit(msg, colors.LOG_ERROR)
        except Exception as err:
            # at least, log to file if log over signal fails
            logging.error(f"Error emitting `error signal` from system exception handler:\n{err}")

        try:
            self.stop_all_seq_tx_threads()
        # self.port_hdlr.deinit_port()
        except Exception as err:
            logging.error(f"Error in final exception handler:\n{err}")
            self.sig_close.emit()


def init_logger(level: int = logging.DEBUG) -> None:
    log_dir = paths.get_default_log_dir()
    os.makedirs(log_dir, exist_ok=True)
    file_path = os.path.join(log_dir, base.LOG_FILENAME)

    fmt = logging.Formatter(base.LOG_FORMAT, datefmt=base.LOG_DATETIME_FORMAT)

    logger = logging.getLogger()
    logger.setLevel(level)

    std_hdlr = logging.StreamHandler()
    std_hdlr.setLevel(level)
    std_hdlr.setFormatter(fmt)
    logger.addHandler(std_hdlr)

    file_hdlr = logging.FileHandler(file_path, encoding="utf-8")
    file_hdlr.setFormatter(fmt)
    file_hdlr.setLevel(level)
    logger.addHandler(file_hdlr)

    asyncio_logger = logging.getLogger("asyncio")
    asyncio_logger.setLevel(logging.WARNING)

    logging.info(f"Logger initialized: {file_path}")


def main() -> None:
    args = cmd_args.SerialToolArgs.parse()
    init_logger(args.log_level)

    app = QtWidgets.QApplication(sys.argv)
    gui = Gui(args)
    gui.show()

    ret = app.exec_()

    sys.exit(ret)


if __name__ == "__main__":
    main()
