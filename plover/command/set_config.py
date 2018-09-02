import ast

COMMAND_DELIMITER = ','


def plugin_error(e, msg):
    """ Add an additional message to an exception before raising to the engine. """
    e.args = (e.args[0] + "\nSET_CONFIG: " + msg,)
    raise e


def set_config(engine, cmdline):
    """
    Set a Plover config option to a given value upon executing a stroke pattern.

    Example usage (enter these lines into dictionary):
    "O*EP": "{PLOVER:SET_CONFIG:translation_frame_opacity,100}",
    "TR*PB": "{PLOVER:SET_CONFIG:translation_frame_opacity,0}",
    """
    # Break down the command string into a key and a value. Throw an error if it isn't in the form of a 2-tuple.
    try:
        key_str, value_str = tuple(cmdline.split(COMMAND_DELIMITER, 1))
    except ValueError as e:
        plugin_error(e,"Bad command string. Command must be in the form {PLOVER:SET_CONFIG:option,value}")
    # Look up the old value of the config setting in order to make sure it's a valid option
    try:
        old_value = engine[key_str]
    except KeyError as e:
        plugin_error(e,"%s is not a valid Plover config option." % key_str)
    # Evaluate the value string to convert to a Python literal.
    try:
        value_obj = ast.literal_eval(value_str)
    except SyntaxError as e:
        plugin_error(e, "Error parsing value string \"%s\"" % value_str)
    # If it is (or can be coerced to) the type of the old value, set the option to the new value.
    try:
        engine[key_str] = value_obj
    except (NameError, TypeError) as e:
        plugin_error(e,"Config value type is incompatible: \"%s\" != %s." % (value_str, type(old_value)))
    except ValueError as e:
        plugin_error(e,"Value \"%s\" is not allowed for config option %s." % (value_str, key_str))
