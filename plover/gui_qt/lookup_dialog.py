
from PyQt5.QtCore import QEvent, Qt

from plover.config import DEFAULT_SEARCH_LIMIT
from plover.translation import unescape_translation

from plover.gui_qt.lookup_dialog_ui import Ui_LookupDialog
from plover.gui_qt.i18n import get_gettext
from plover.gui_qt.tool import Tool


_ = get_gettext()


class LookupDialog(Tool, Ui_LookupDialog):

    ''' Search the dictionary for translations. '''

    TITLE = _('Lookup')
    ICON = ':/lookup.svg'
    ROLE = 'lookup'
    SHORTCUT = 'Ctrl+L'

    def __init__(self, engine):
        super().__init__(engine)
        self.setupUi(self)
        self.search_limit = DEFAULT_SEARCH_LIMIT
        engine.signal_connect('config_changed', self.on_config_changed)
        self.on_config_changed(engine.config)
        self.pattern.installEventFilter(self)
        self.suggestions.installEventFilter(self)
        self.pattern.setFocus()
        self.restore_state()
        self.finished.connect(self.save_state)

    def on_config_changed(self, config_update):
        if 'search_display_limit' in config_update:
            self.search_limit = config_update.get('search_display_limit')

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress and \
           event.key() in (Qt.Key_Enter, Qt.Key_Return):
            return True
        return False

    def _update_suggestions(self, suggestion_list):
        self.suggestions.clear()
        self.suggestions.append(suggestion_list, keep_position=True)

    def on_lookup(self, pattern):
        # Wherever a character is typed or a checkbox is changed, refresh the lookup results.
        # TODO: preserve the state of search mode checkboxes?
        translation = unescape_translation(pattern.strip())
        suggestion_list = self._engine.get_suggestions(translation,
                                                       count=self.search_limit,
                                                       partial=self.partialCheck.isChecked(),
                                                       regex=self.regexCheck.isChecked())
        self._update_suggestions(suggestion_list)

    def on_mode_change(self, state):
        self.on_lookup(self.pattern.text())
