#!/usr/bin/env python
import os
if os.environ.get('USER','') == 'vagrant':
    del os.link

import distutils.core

distutils.core.setup(
	name = "arago-common-base",
	version = "2.3",
	author = "Marcus Klemm",
	author_email = "mklemm@arago.de",
	description = ("Common functions and classes"),
	license = "MIT",
	url = "http://www.arago.de",
	long_description="Common functions and classes",
	classifiers=[
		"Development Status :: 5 - Production/Stable",
		"Topic :: Utilities",
		"License :: OSI Approved :: MIT License",
	],
	packages=['arago.common.configparser',
	          'arago.common.daemon',
	          'arago.common.helper',
	          'arago.common.meta',
	          'arago.common.logging',
	          'arago.common.backoff',
	          'arago.common.stopwatch',
	          'arago.common.lists',
	          'arago.common.gssapi',
	          'arago.common.processor',
	]
)
