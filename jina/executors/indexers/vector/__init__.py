import gzip
from os import path
from typing import Optional

import numpy as np

from .. import BaseVectorIndexer


class BaseNumpyIndexer(BaseVectorIndexer):
    """:class:`BaseNumpyIndexer` stores and loads vector in a compresses binary file """

    def __init__(self,
                 compress_level: int = 1,
                 *args, **kwargs):
        """
        :param compress_level: The compresslevel argument is an integer from 0 to 9 controlling the
                        level of compression; 1 is fastest and produces the least compression,
                        and 9 is slowest and produces the most compression. 0 is no compression
                        at all. The default is 9.

        .. note::
            Metrics other than `cosine` and `euclidean` requires ``scipy`` installed.

        """
        super().__init__(*args, **kwargs)
        self.num_dim = None
        self.dtype = None
        self.compress_level = compress_level
        self.key_bytes = b''
        self.key_dtype = None

    def get_add_handler(self):
        """Open a binary gzip file for adding new vectors

        :return: a gzip file stream
        """
        return gzip.open(self.index_abspath, 'ab', compresslevel=self.compress_level)

    def get_create_handler(self):
        """Create a new gzip file for adding new vectors

        :return: a gzip file stream
        """
        return gzip.open(self.index_abspath, 'wb', compresslevel=self.compress_level)

    def add(self, keys: 'np.ndarray', vectors: 'np.ndarray', *args, **kwargs):
        if len(vectors.shape) != 2:
            raise ValueError(f'vectors shape {vectors.shape} is not valid, expecting "vectors" to have rank of 2')

        if not self.num_dim:
            self.num_dim = vectors.shape[1]
            self.dtype = vectors.dtype.name
        elif self.num_dim != vectors.shape[1]:
            raise ValueError(
                "vectors' shape [%d, %d] does not match with indexers's dim: %d" %
                (vectors.shape[0], vectors.shape[1], self.num_dim))
        elif self.dtype != vectors.dtype.name:
            raise TypeError(
                "vectors' dtype %s does not match with indexers's dtype: %s" %
                (vectors.dtype.name, self.dtype))
        elif keys.shape[0] != vectors.shape[0]:
            raise ValueError('number of key %d not equal to number of vectors %d' % (keys.shape[0], vectors.shape[0]))
        elif self.key_dtype != keys.dtype.name:
            raise TypeError(
                "keys' dtype %s does not match with indexers keys's dtype: %s" %
                (keys.dtype.name, self.key_dtype))

        self.write_handler.write(vectors.tobytes())
        self.key_bytes += keys.tobytes()
        self.key_dtype = keys.dtype.name
        self._size += keys.shape[0]

    def get_query_handler(self) -> Optional['np.ndarray']:
        """Open a gzip file and load it as a numpy ndarray

        :return: a numpy ndarray of vectors
        """
        vecs = self.raw_ndarray
        if vecs is not None:
            return self.build_advanced_index(vecs)
        else:
            return None

    def build_advanced_index(self, vecs: 'np.ndarray'):
        raise NotImplementedError

    def _load_gzip(self, abspath):
        self.logger.info(f'loading index from {abspath}...')
        if not path.exists(abspath):
            self.logger.warning('numpy data not found: {}'.format(abspath))
            return None
        result = None
        try:
            if self.num_dim and self.dtype:
                with gzip.open(abspath, 'rb') as fp:
                    result = np.frombuffer(fp.read(), dtype=self.dtype).reshape([-1, self.num_dim])
        except EOFError:
            self.logger.error(
                f'{self.index_abspath} is broken/incomplete, perhaps forgot to ".close()" in the last usage?')
        return result

    @property
    def raw_ndarray(self):
        vecs = self._load_gzip(self.index_abspath)
        if vecs is None:
            return vecs

        if self.key_bytes and self.key_dtype:
            self.int2ext_key = np.frombuffer(self.key_bytes, dtype=self.key_dtype)

        if self.int2ext_key is not None and vecs is not None and vecs.ndim == 2:
            if self.int2ext_key.shape[0] != vecs.shape[0]:
                self.logger.error(
                    f'the size of the keys and vectors are inconsistent ({self.int2ext_key.shape[0]} != {vecs.shape[0]}), '
                    f'did you write to this index twice?')
                return None
            if vecs.shape[0] == 0:
                self.logger.warning(f'an empty index is loaded')
            return vecs
        else:
            return None
