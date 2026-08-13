"""Business logic, kept out of the routers.

A router's job is HTTP: read the request, call something, shape the response. When
domain rules live in routers they cannot be tested without spinning up a web server,
and they get quietly duplicated the first time a second route needs them.
"""
