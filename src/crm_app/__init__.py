"""crm-app: a multi-tenant CRM product built on the external SaaS-OS package.

Importing this package reads no configuration and touches no service.
SaaS-OS resolves its configuration when its modules are imported, so the
entrypoints (`crm_app.app`, `crm_app.worker`, `crm_app.migrate`) validate the
environment first (`crm_app.settings`) and import SaaS-OS only afterwards.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("crm-app")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0"
