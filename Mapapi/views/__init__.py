"""
Mapapi.views package.

Re-exports every view from each domain module so that legacy code using
`from Mapapi.views import *` (or specific symbols) keeps working unchanged.
"""
from .common import *  # noqa: F401,F403
from .organisation import *  # noqa: F401,F403
from .user import *  # noqa: F401,F403
from .elu import *  # noqa: F401,F403
from .incident import *  # noqa: F401,F403
from .impact import *  # noqa: F401,F403
from .evenement import *  # noqa: F401,F403
from .contact import *  # noqa: F401,F403
from .communaute import *  # noqa: F401,F403
from .rapport import *  # noqa: F401,F403
from .participate import *  # noqa: F401,F403
from .zone import *  # noqa: F401,F403
from .message import *  # noqa: F401,F403
from .category import *  # noqa: F401,F403
from .indicateur import *  # noqa: F401,F403
from .image_background import *  # noqa: F401,F403
from .overpass import *  # noqa: F401,F403
from .collaboration import *  # noqa: F401,F403
from .prediction import *  # noqa: F401,F403
from .notification import *  # noqa: F401,F403
from .misc import *  # noqa: F401,F403
from .task import *  # noqa: F401,F403
from .partner_suggestion import *  # noqa: F401,F403
from .auth_cookie import *  # noqa: F401,F403
