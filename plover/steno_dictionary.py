# Copyright (c) 2013 Hesky Fisher.
# See LICENSE.txt for details.

""" StenoDictionary class and related functions.
    A steno dictionary maps sequences of steno strokes to translations. """

import collections
import os
import shutil

from plover.dictionary.base import ReverseStenoDict
from plover.resource import ASSET_SCHEME, resource_filename, resource_timestamp


class StenoDictionary(dict):
    """ A steno dictionary.

    This dictionary maps immutable sequences to translations and tracks the
    length of the longest key. It also keeps a reverse mapping of translations
    back to sequences and allows searching from it.

    Attributes:
    filters -- Unused
    timestamp -- File last modification time, used to detect external changes.
    readonly -- Is an attribute of the class and of instances.
        class: If True, new instances of the class may not be created through the create() method.
        instances: If True, the dictionary may not be modified, nor may it be written to the path on disk.
    enabled -- If True, dictionary is included in lookups by a StenoDictionaryCollection
    path -- File path where dictionary contents are stored on disk

    """

    # False if class supports creation.
    readonly = False

    def __init__(self):
        super().__init__()
        # Reverse dictionary matches translations to keys by exact match or by "similarity" if required.
        self.reverse = ReverseStenoDict()
        self.filters = []
        self.timestamp = 0
        self.readonly = False
        self.enabled = True
        self.path = None
        # The special search methods are simple pass-throughs to the reverse dictionary
        self.similar_reverse_lookup = self.reverse.get_similar_keys
        self.partial_reverse_lookup = self.reverse.partial_match_keys
        self.regex_reverse_lookup = self.reverse.regex_match_keys

    def __str__(self):
        return '%s(%r)' % (self.__class__.__name__, self.path)

    def __repr__(self):
        return str(self)

    @classmethod
    def create(cls, resource):
        assert not resource.startswith(ASSET_SCHEME)
        if cls.readonly:
            raise ValueError('%s does not support creation' % cls.__name__)
        d = cls()
        d.path = resource
        return d

    @classmethod
    def load(cls, resource):
        filename = resource_filename(resource)
        timestamp = resource_timestamp(filename)
        d = cls()
        d._load(filename)
        if resource.startswith(ASSET_SCHEME) or \
           not os.access(filename, os.W_OK):
            d.readonly = True
        d.path = resource
        d.timestamp = timestamp
        return d

    def save(self):
        assert not self.readonly
        filename = resource_filename(self.path)
        # Write the new file to a temp location.
        tmp = filename + '.tmp'
        self._save(tmp)
        timestamp = resource_timestamp(tmp)
        # Then move the new file to the final location.
        shutil.move(tmp, filename)
        # And update our timestamp.
        self.timestamp = timestamp

    # Actual methods to load and save dictionary contents to files must be implemented by format-specific subclasses.
    def _load(self, filename):
        raise NotImplementedError()

    def _save(self, filename):
        raise NotImplementedError()

    def clear(self):
        """ Empty the dictionary without altering its file-based attributes. """
        super().clear()
        self.reverse.clear()

    def __setitem__(self, key, value):
        assert not self.readonly
        # Be careful here. If the key already exists, we have to remove its old mapping from the reverse dictionary
        # while we can still find it. And if it's a new key, it could possibly be the new longest one.
        if key in self:
            self.reverse.remove_key(self[key], key)
        super().__setitem__(key, value)
        self.reverse.append_key(value, key)

    def __delitem__(self, key):
        assert not self.readonly
        value = super().pop(key)
        self.reverse.remove_key(value, key)

    def update(self, *args, **kwargs):
        """ Update the dictionary using a single iterable sequence of (key, value) tuples or a single mapping
            located in args. kwargs is irrelevant since only strings can be keywords, but is included for
            method signature compatibility with dict. """
        assert not self.readonly
        if not self:
            # Fast path for when the dicts start out empty
            super().update(*args, **kwargs)
            self.reverse.match_forward(self)
        else:
            # Update dicts one item at a time
            for (k, v) in dict(*args, **kwargs).items():
                self[k] = v

    def reverse_lookup(self, value):
        """
        Return a list of keys that can exactly produce the given value.
        If there aren't any keys that produce this value, just return an empty list.
        """
        return self.reverse[value] if value in self.reverse else []

    def casereverse_lookup(self, value):
        """ Return a list of translations case-insensitive equal to the given value. For backwards compatibility. """
        return [v for v in self.similar_reverse_lookup(value) if value.lower() == v.lower()]

    # Unimplemented methods from base class that are unsafe (can mutate the object)
    def setdefault(self, k, default=None): return NotImplementedError
    def pop(self, k): return NotImplementedError
    def popitem(self): return NotImplementedError

class StenoDictionaryCollection:

    def __init__(self, dicts=[]):
        self.dicts = []
        self.filters = []
        self.set_dicts(dicts)

    def set_dicts(self, dicts):
        self.dicts = dicts[:]

    def lookup(self, key):
        """ Perform a lookup on each enabled dictionary in priority order.
            Return the value of the first entry that matches the key, or None if the key isn't found anywhere.
            Immediately return None if a matching key-value pair is caught by one of the filters. """
        for d in self.dicts:
            if d.enabled and key in d:
                value = d[key]
                for f in self.filters:
                    if f(key, value):
                        return None
                return value

    def raw_lookup(self, key):
        """ Perform a simple lookup on each enabled dictionary in priority order with no filters.
            Return the value of the first entry that matches the key, or None if the key isn't found anywhere. """
        for d in self.dicts:
            if d.enabled and key in d:
                return d[key]

    def __str__(self):
        return 'StenoDictionaryCollection' + repr(tuple(self.dicts))

    def __repr__(self):
        return str(self)

    def reverse_lookup(self, value):
        """ Return a set of keys that can exactly produce the given value under the current dictionary precedence. """
        keys = set()
        keys_update = keys.update
        # Loop over enabled dictionaries from low to high priority
        for d in reversed(self.dicts):
            if d.enabled:
                # Remove overridden keys that came from previous (lower-priority) dictionaries
                if keys:
                    overrides = {k for k in keys if k in d}
                    keys -= overrides
                # Add the keys from this dictionary
                keys_update(d.reverse_lookup(value))
        return keys

    def _multi_reverse_lookup(self, values, max_count=None):
        """
        Perform a reverse lookup across all enabled dictionaries with the given translations.
        Filter out the ones that are either duplicates or impossible to produce due to key overrides.
        Return the rest in a sorted list, each one paired in a tuple with a set of keys that can produce it.
        If max_count is given, only return up to that many valid results.
        """
        results = []
        old_v = None
        reverse_lookup = self.reverse_lookup
        results_append = results.append
        for v in sorted(values, key=str.lower):
            if v is not old_v:
                old_v = v
                keys = reverse_lookup(v)
                if keys:
                    results_append((v, keys))
                    if max_count is not None and len(results) >= max_count:
                        break
        return results

    def find_similar(self, value):
        """
        Return a list of similar (or equal) translations to the given value across all enabled dictionaries,
        each paired in a tuple with a set of keys that will produce it given the current dictionary precedence.
        """
        translations = [t for d in self.dicts if d.enabled for t in d.similar_reverse_lookup(value)]
        return self._multi_reverse_lookup(translations)

    def find_partial(self, pattern, count=None):
        """
        Return a list of translations that are similar, equal to, or supersets of the given value across all
        enabled dictionaries, each paired in a tuple with a set of keys that will produce it given the current
        dictionary precedence. After translations that compare similar, the next ones in the sort order
        will usually be supersets. ("test" could return entries for "test", "tested", "testing")
        """
        translations = [t for d in self.dicts if d.enabled for t in d.partial_reverse_lookup(pattern, count)]
        return self._multi_reverse_lookup(translations, count)

    def find_regex(self, pattern, count=None):
        """
        Return a list of translations that match the given regular expression across all enabled dictionaries,
        each paired in a tuple with a set of keys that will produce it given the current dictionary precedence.
        If count is given, only return up to that many total matches.
        """
        translations = [t for d in self.dicts if d.enabled for t in d.regex_reverse_lookup(pattern, count)]
        return self._multi_reverse_lookup(translations, count)

    def casereverse_lookup(self, value):
        """ Find translations that are case-insensitive equal to the given value across all enabled dictionaries.
            Only returns a list of translations, not the keys that produce them. For backwards-compatibility. """
        return [v for (v, _) in self.find_similar(value) if value.lower() == v.lower()]

    def first_writable(self):
        '''Return the first writable dictionary.'''
        for d in self.dicts:
            if not d.readonly:
                return d
        raise KeyError('no writable dictionary')

    def set(self, key, value, path=None):
        if path is None:
            d = self.first_writable()
        else:
            d = self[path]
        d[key] = value

    def save(self, path_list=None):
        '''Save the dictionaries in <path_list>.

        If <path_list> is None, all writable dictionaries are saved'''
        if path_list is None:
            dict_list = [d for d in self if dictionary.save is not None]
        else:
            dict_list = [self[path] for path in path_list]
        for d in dict_list:
            d.save()

    def get(self, path):
        for d in self.dicts:
            if d.path == path:
                return d

    def __getitem__(self, path):
        d = self.get(path)
        if d is None:
            raise KeyError(repr(path))
        return d

    def __iter__(self):
        for d in self.dicts:
            yield d.path

    def add_filter(self, f):
        self.filters.append(f)

    def remove_filter(self, f):
        self.filters.remove(f)
