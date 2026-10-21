"""HTTP routes owned by this product, mounted onto the SaaS-OS application
by `crm_app.app.create_app()`. Every route declares exactly one SaaS-OS
route policy (`saas_os.api.dependencies.require_permission`); the platform
refuses to start otherwise.

Importing a route module resolves SaaS-OS configuration, so only
`create_app()` imports them, after the settings have been validated.
"""
