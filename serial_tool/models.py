import enum
from typing import Generic, List, Optional, TypeVar

from PyQt5 import QtCore

from serial_tool.defines import colors
from serial_tool.defines import ui_defs
from serial_tool import serial_hdlr


class OutputRepresentation(enum.IntEnum):
    STRING = 0
    INT_LIST = 1
    HEX_LIST = 2
    ASCII_LIST = 3


class SequenceInfo:
    def __init__(self, ch_idx: int, delay_msec: int = 0, repeat: int = 1):
        """Container of parsed block of sequence data

        Args:
            ch_idx: index of data channel field (starting with zero).
            delay_msec: delay after this channel data is sent in milliseconds.
            repeat: number of times this channel is sent with given data and delay.
        """
        self.ch_idx: int = ch_idx
        self.delay_msec: int = delay_msec
        self.repeat: int = repeat

    def __str__(self):
        return (
            f"{ui_defs.SEQ_BLOCK_START_CHAR}{self.ch_idx}{ui_defs.SEQ_BLOCK_DATA_SEPARATOR} "
            f"{self.delay_msec}{ui_defs.SEQ_BLOCK_DATA_SEPARATOR} "
            f"{self.repeat}{ui_defs.SEQ_BLOCK_END_CHAR}"
        )


class TextFieldStatus(enum.Enum):
    OK = "valid"
    BAD = "invalid"
    EMPTY = "no content"

    @staticmethod
    def get_color(status: "TextFieldStatus") -> str:
        if status == TextFieldStatus.OK:
            return colors.INPUT_VALID
        if status == TextFieldStatus.BAD:
            return colors.INPUT_ERROR
        if status == TextFieldStatus.EMPTY:
            return colors.INPUT_NONE

        raise ValueError(f"Unable to determine color for status: {status}")


T_DATA_TYPE = TypeVar("T_DATA_TYPE")


class _TextFieldParserResult(Generic[T_DATA_TYPE]):
    def __init__(self, status: TextFieldStatus, msg: str = "", data: Optional[T_DATA_TYPE] = None) -> None:
        self.status = status
        self.msg = msg

        self._data = data

    @property
    def data(self) -> T_DATA_TYPE:
        assert self._data is not None

        return self._data


class ChannelTextFieldParserResult(_TextFieldParserResult[List[int]]):
    def __init__(self, status: TextFieldStatus, msg: str = "", data: Optional[List[int]] = None) -> None:
        super().__init__(status, msg, data)


class SequenceTextFieldParserResult(_TextFieldParserResult[List[SequenceInfo]]):
    def __init__(self, status: TextFieldStatus, msg: str = "", data: Optional[List[SequenceInfo]] = None) -> None:
        super().__init__(status, msg, data)


class SharedSignalsContainer:
    def __init__(
        self, write: QtCore.pyqtBoundSignal, warning: QtCore.pyqtBoundSignal, error: QtCore.pyqtBoundSignal
    ) -> None:
        self.write = write
        self.warning = warning
        self.error = error


class RuntimeDataCache(QtCore.QObject):
    sig_serial_settings_update = QtCore.pyqtSignal()
    sig_data_field_update = QtCore.pyqtSignal(int)
    sig_note_field_update = QtCore.pyqtSignal(int)
    sig_seq_field_update = QtCore.pyqtSignal(int)
    sig_rx_display_update = QtCore.pyqtSignal()
    sig_tx_display_update = QtCore.pyqtSignal()
    sig_out_representation_update = QtCore.pyqtSignal()
    sig_new_line_on_rx_update = QtCore.pyqtSignal()
    sig_new_line_on_rx_timeout_update = QtCore.pyqtSignal()

    def __init__(self) -> None:
        """Main shared data object."""
        super().__init__()

        self.serial_settings = serial_hdlr.SerialCommSettings()

        self.cfg_file_path: Optional[str] = None

        self.data_fields: List[str] = [""] * ui_defs.NUM_OF_DATA_CHANNELS
        self.parsed_data_fields: List[Optional[List[int]]] = [None] * ui_defs.NUM_OF_DATA_CHANNELS
        self.note_fields: List[str] = [""] * ui_defs.NUM_OF_DATA_CHANNELS

        self.seq_fields: List[str] = [""] * ui_defs.NUM_OF_SEQ_CHANNELS
        self.parsed_seq_fields: List[Optional[List[SequenceInfo]]] = [None] * ui_defs.NUM_OF_SEQ_CHANNELS

        self.all_rx_tx_data: List[str] = []

        self.output_data_representation = OutputRepresentation.STRING
        self.display_rx_data = True
        self.display_tx_data = True
        self.new_line_on_rx = False
        self.new_line_on_rx_timeout_msec: int = ui_defs.DEFAULT_RX_NEWLINE_TIMEOUT_MS

    def set_serial_settings(self, settings: serial_hdlr.SerialCommSettings) -> None:
        """Update serial settings and emit a signal at the end."""
        self.serial_settings = settings
        self.sig_serial_settings_update.emit()

    def set_data_field(self, channel: int, data: str) -> None:
        """Update data field and emit a signal at the end."""
        self.data_fields[channel] = data
        self.sig_data_field_update.emit(channel)
        # self.data_fields = data
        # self.sig_data_field_update.emit()
    # def set_data_field(self, data: str) -> None:
    #     """Update RX new line timeout field (timeout after \n is appended to next RX data)
    #     and emit a signal at the end."""
    #     self.data_fields = data
    #     self.sig_data_field_update.emit(0)


    def set_note_field(self, channel: int, data: str) -> None:
        """Update note field and emit a signal at the end."""
        self.note_fields[channel] = data
        self.sig_note_field_update.emit(channel)

    def set_seq_field(self, channel: int, data: str) -> None:
        """Update sequence field and emit a signal at the end."""
        self.seq_fields[channel] = data
        self.sig_seq_field_update.emit(channel)

    def set_rx_display_ode(self, is_enabled: bool) -> None:
        """Update RX log visibility field and emit a signal at the end."""
        self.display_rx_data = is_enabled
        self.sig_rx_display_update.emit()

    def set_tx_display_mode(self, is_enabled: bool) -> None:
        """Update TX log visibility field and emit a signal at the end."""
        self.display_tx_data = is_enabled
        self.sig_tx_display_update.emit()

    def set_output_representation_mode(self, mode: OutputRepresentation) -> None:
        """Update output representation field and emit a signal at the end."""
        self.output_data_representation = mode
        self.sig_out_representation_update.emit()

    def set_new_line_on_rx_mode(self, is_enabled: bool) -> None:
        """Update RX new line field and emit a signal at the end."""
        self.new_line_on_rx = is_enabled
        self.sig_new_line_on_rx_update.emit()

    def set_new_line_on_rx_timeout(self, timeout_msec: int) -> None:
        """Update RX new line timeout field (timeout after \n is appended to next RX data)
        and emit a signal at the end."""
        self.new_line_on_rx_timeout_msec = timeout_msec
        self.sig_new_line_on_rx_timeout_update.emit()
