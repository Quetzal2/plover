""" Unit tests for built-in engine command plugins. """

import ast
import operator
import pytest
from collections import namedtuple

from plover.config import Config
from plover.command.set_config import set_config, COMMAND_DELIMITER
from test.test_config import DEFAULTS, DEFAULT_KEYMAP


def test_set_config():
    # Test a command string for at least one of each option type.
    # Config values are sometimes converted and stored as different types than the input,
    # so include a test condition that may be different from strict equality.
    # For expected failures, this is replaced with the exception it should cause.
    TestCmd = namedtuple('TestCmd', 'cmdstr test_condition')

    tests = [TestCmd('space_placement,"After Output"',
                     operator.eq),
             TestCmd('start_attached,True',
                     operator.eq),
             TestCmd('undo_levels,10',
                     operator.eq),
             TestCmd('undo_levels10',  # Bad command format
                     ValueError),
             TestCmd('undo_levels,"does a string work?"',  # Bad value type
                     ValueError),
             TestCmd('log_file_name,"c:/whatever/morestrokes.log"',
                     operator.eq),
             TestCmd('enabled_extensions,[]',  # May be any empty sequence
                     lambda x, y: len(x) == 0 and len(y) == 0),
             TestCmd('machine_type,"Keyboard"',
                     operator.eq),
             TestCmd('machine_type,"Telepathy"',  # Unsupported value
                     ValueError),
             TestCmd('blood_type,"O-"',  # Not a valid key
                     KeyError),
             TestCmd('machine_specific_options,{"arpeggiate": True}',
                     operator.eq),
             TestCmd('machine_specific_options,{"left off the brace": True',  # Bad string format
                     SyntaxError),
             TestCmd("system_keymap,"+str(DEFAULT_KEYMAP),  # Check if all the keymap's keys are present
                     (lambda x, y:any(s in y for s in dict(x)))),
             TestCmd('dictionaries,("user.json", "commands.json", "main.json")',  # Check if all the dict paths match
                     (lambda x, y:all(s in d.path for (s,d) in zip(x,y))))]

    cfg = Config()
    cfg.update(**DEFAULTS)
    # Plugin only uses get and set item, which pass straight through the engine to Config.
    # This means we can pass Config directly into the plugin instead of mocking an engine.
    for (cmdstr, test_condition) in tests:
        # For each correct command, make sure the value made it in and back out acceptably.
        # For each incorrect one (condition is an Exception subclass), make sure the exception was raised.
        if isinstance(test_condition, type) and issubclass(test_condition, Exception):
            with pytest.raises(test_condition):
                set_config(cfg, cmdstr)
        else:
            set_config(cfg, cmdstr)
            (key, value) = cmdstr.split(COMMAND_DELIMITER, 1)
            test_result = test_condition(ast.literal_eval(value), cfg[key])
            assert test_result
