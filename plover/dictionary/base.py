# Copyright (c) 2013 Hesky Fisher
# See LICENSE.txt for details.

# TODO: maybe move this code into the StenoDictionary itself. The current saver 
# structure is odd and awkward.
# TODO: write tests for this file

"""Common elements to all dictionary formats."""

from os.path import splitext
from bisect import bisect_left
import functools
import operator
import threading

from plover.registry import registry


def _get_dictionary_class(filename):
    extension = splitext(filename)[1].lower()[1:]
    try:
        dict_module = registry.get_plugin('dictionary', extension).obj
    except KeyError:
        raise ValueError(
            'Unsupported extension: %s. Supported extensions: %s' %
            (extension, ', '.join(plugin.name for plugin in
                                  registry.list_plugins('dictionary'))))
    return dict_module

def _locked(fn):
    lock = threading.Lock()
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with lock:
            fn(*args, **kwargs)
    return wrapper

def _threaded(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        t = threading.Thread(target=fn, args=args, kwargs=kwargs)
        t.start()
    return wrapper

def create_dictionary(resource, threaded_save=True):
    '''Create a new dictionary.

    The format is inferred from the extension.

    Note: the file is not created! The resulting dictionary save
    method must be called to finalize the creation on disk.
    '''
    d = _get_dictionary_class(resource).create(resource)
    if threaded_save:
        d.save = _threaded(_locked(d.save))
    return d

def load_dictionary(resource, threaded_save=True):
    '''Load a dictionary from a file.

    The format is inferred from the extension.
    '''
    d = _get_dictionary_class(resource).load(resource)
    if not d.readonly and threaded_save:
        d.save = _threaded(_locked(d.save))
    return d


class SimilarSearchDict(dict):
    """
    A special dictionary implementation using a sorted key list along with the usual hash map. This allows lookups
    for keys that are "similar" to a given key in O(log n) time as well as exact O(1) hash lookups, at the cost of
    extra memory to store transformed keys and increasing item insertion and deletion to average between O(log n) and
    O(n) amortized time (depending on how often new items are added between searches). No penalty is incurred for
    changing the values of existing items. The worst case is when item insertions and deletions/searches are done
    alternately. It is most useful for dictionaries whose items are inserted/deleted rarely, and which have a need
    to compare and sort their keys by some measure other than their natural sorting order (if they have one).

    The "similarity function" returns a measure of how close two keys are to one another. This function should take a
    single key as input, and the return values should compare equal for keys that are deemed to be "similar". Even if
    they are not equal, keys with return values that are close will be close together in the list and may appear
    together in a search where equality is not required (i.e get_similar with count defined). All implemented
    functionality other than similarity search is equivalent to that of a regular dictionary.

    The keys must be of a type that is immutable, hashable, and totally orderable (i.e. it is possible to rank all the
    keys from least to greatest using comparisons) both before and after applying the given similarity function.

    Inside the list, keys are stored in sorted order as tuples of (simkey, rawkey), which means they are ordered first
    by the value computed by the similarity function, and if those are equal, then by their natural value.
    """

    def __init__(self, simfn=None, *args, **kwargs):
        """ Initialize the dict and list to empty, and set the sort flag.
            The first argument sets the similarity function. It is the identity function if None or not provided.
            If other arguments were given, treat them as sets of initial items to add as with dict.update(). """
        super().__init__()
        self._list = []
        self._needs_sorting = False
        if simfn is not None:
            self._simfn = simfn
        else:
            self._simfn = lambda x: x
        if args or kwargs:
            self.update(*args, **kwargs)

    def clear(self):
        super().clear()
        self._list.clear()

    def __setitem__(self, k, v):
        """ Set an item in the dict. If the key didn't exist before, add it to the list and set the sort flag. """
        if k not in self:
            self._list.append((self._simfn(k), k))
            self._needs_sorting = True
        super().__setitem__(k, v)

    def __delitem__(self, k):
        """
        Delete an item in the dict+list (if it exists). Deleting an item will not affect the order of the list,
        but it has to be sorted in order to find the key using bisection. We could look for the key the slow way
        under O(n) time, but sorting the list is only O(n log n) or less and will need to be done anyway for
        searches or further deletions.
        """
        if k in self:
            super().__delitem__(k)
            if self._needs_sorting:
                self.sort()
            idx = bisect_left(self._list, (self._simfn(k), k))
            del self._list[idx]

    def update(self, *args, **kwargs):
        """ Update the dict using items from given arguments. Because this is typically used to fill dictionaries with
            large amounts of items, a fast path is included if ours is empty, and the list is immediately sorted. """
        if not self:
            super().update(*args, **kwargs)
            self._list = list(zip(map(self._simfn, self), self))
        else:
            for (k, v) in dict(*args, **kwargs).items():
                self[k] = v
        self.sort()

    def sort(self):
        """ Perform a sort on the list. Is done when necessary; can also be done manually during initialization. """
        self._list.sort()
        self._needs_sorting = False

    def _index_left(self, k):
        """ Sort the list if necessary, then find the leftmost index to the given key under the similarity function. """
        if self._needs_sorting:
            self.sort()
        # Out of all tuples with an equal first value, the 1-tuple with this value compares less than any 2-tuple.
        return bisect_left(self._list, (self._simfn(k),))

    def filter_keys(self, k, count=None, filterfn=None):
        """ Filter the list of keys starting from the position where k is/would be and return up to <count> matches,
            or all matches if count is None. The filter function is a T/F comparison between each list key and the
            given key after both have been altered by the similarity function; if None, all keys are returned. """
        _list = self._list
        simkey = self._simfn(k)
        idx = self._index_left(k)
        keys = []
        while idx < len(_list):
            (sk, rk) = _list[idx]
            if filterfn is not None and not filterfn(sk, simkey):
                break
            keys.append(rk)
            if count is not None and len(keys) >= count:
                break
            idx += 1
        return keys

    def get_similar_keys(self, k, count=None):
        """ Get a list of similar keys to the given key (they compare equal under the similarity function). """
        return self.filter_keys(k, count=count, filterfn=operator.eq)

    # Unimplemented methods from base class that are unsafe (can mutate the object)
    def setdefault(self, k, default=None): return NotImplementedError
    def pop(self, k): return NotImplementedError
    def popitem(self): return NotImplementedError
