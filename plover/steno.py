# Copyright (c) 2010-2011 Joshua Harlan Lifton.
# See LICENSE.txt for details.

# TODO: unit test this file

"""Generic stenography data models.

This module contains the following class:

Stroke -- A data model class that encapsulates a sequence of steno keys.

"""

import re

from plover import system


STROKE_DELIMITER = '/'

_NUMBERS = set('0123456789')
_IMPLICIT_NUMBER_RX = re.compile('(^|[1-4])([6-9])')

def normalize_stroke(stroke):
    letters = set(stroke)
    if letters & _NUMBERS:
        if system.NUMBER_KEY in letters:
            stroke = stroke.replace(system.NUMBER_KEY, '')
        # Insert dash when dealing with 'explicit' numbers
        m = _IMPLICIT_NUMBER_RX.search(stroke)
        if m is not None:
            start = m.start(2)
            return stroke[:start] + '-' + stroke[start:]
    if '-' in letters:
        if stroke.endswith('-'):
            stroke = stroke[:-1]
        elif letters & system.IMPLICIT_HYPHENS:
            stroke = stroke.replace('-', '')
    return stroke

def normalize_steno(strokes_string):
    """Convert steno strings to one common form."""
    return tuple(normalize_stroke(stroke) for stroke
                 in strokes_string.split(STROKE_DELIMITER))

def sort_steno_keys(steno_keys):
    return sorted(steno_keys, key=system.KEY_ORDER.__getitem__)

def sort_steno_strokes(strokes_list):
    """ Return suggestions, sorted by fewest strokes, then fewest keys. """
    return sorted(strokes_list, key=lambda x: (sum(c == "/" for c in x), len(x)))


class Stroke(set):
    """
    A standardized data model for stenotype machine strokes.

    This class standardizes the representation of a stenotype chord. A stenotype
    chord can be any sequence of stenotype keys that can be simultaneously
    pressed. Nearly all stenotype machines offer the same set of keys that can
    be combined into a chord, though some variation exists due to duplicate
    keys. This class accounts for such duplication, imposes the standard
    stenographic ordering on the keys, and combines the keys into a single
    string (called RTFCRE for historical reasons).

    The class itself is a set of steno keys, with the following attributes:
    steno_keys:    A sorted list of the contained keys.
    rtfcre:        String representation of the sorted keys.
    is_correction: True if the stroke consists solely of the undo key.
    """

    def __init__(self, steno_keys):
        """ Create a steno stroke by formatting steno keys.

        Arguments:

        steno_keys -- A container of pressed keys.

        """
        # Remove duplicate keys and save the rest in the set.
        super().__init__(steno_keys)

        # Convert strokes involving the number bar to numbers.
        if system.NUMBER_KEY in self:
            numerals = self.intersection(system.NUMBERS)
            if numerals:
                self.remove(system.NUMBER_KEY)
                for k in numerals:
                    self.remove(k)
                    self.add(system.NUMBERS[k])

        # Sort the keys into a list and build an RTFCRE string out of them.
        self.steno_keys = sort_steno_keys(self)
        if self & system.IMPLICIT_HYPHEN_KEYS:
            self.rtfcre = ''.join(key.strip('-') for key in self.steno_keys)
        else:
            pre = ''.join(k.strip('-') for k in self.steno_keys if k[-1] == '-'
                          or k == system.NUMBER_KEY)
            post = ''.join(k.strip('-') for k in self.steno_keys if k[0] == '-')
            self.rtfcre = '-'.join([pre, post]) if post else pre

        # Determine if this stroke is a correction stroke.
        self.is_correction = (self.rtfcre == system.UNDO_STROKE_STENO)

    def __str__(self):
        if self.is_correction:
            prefix = '*'
        else:
            prefix = ''
        return '%sStroke(%s : %s)' % (prefix, self.rtfcre, self.steno_keys)

    def __repr__(self):
        return str(self)
