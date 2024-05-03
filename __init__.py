from __future__ import unicode_literals, division, absolute_import, print_function

__license__   = 'GPL v3'
__copyright__ = '2024, IncrediblePineapple'

# The class that all Interface Action plugin wrappers must inherit from
from calibre.customize import InterfaceActionBase

class ActionCollectionTitles(InterfaceActionBase):
  name                    = 'Collection title creator plugin'
  description             = 'Insert collection titles into ePubs without doing a conversion'
  supported_platforms     = ['windows', 'osx', 'linux']
  author                  = 'IncrediblePineapple'
  version                 = (1, 0, 0)
  minimum_calibre_version = (2, 85, 1)

  actual_plugin           = 'calibre_plugins.collection_titles.main:CollectionTitlesAction'