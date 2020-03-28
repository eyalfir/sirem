from setuptools import setup

setup(name='sirem',
      description='SImple RElease Manager tool',
      author='Eyal Firstenberg',
      author_email='eyalfir@gmail.com',
      packages=['sirem'],
      install_requires=['PyYAML>=5.3.1', 'requests>=2.23.0', 'jira>=2.0.0', 'Jinja2>=2.10', 'pypandoc>=1.4'],
      scripts=['bin/sirem'],
      setup_requires=['setuptools_scm'],
      package_data = {
        'sirem': ['report.template.md', 'github-pandoc.css'],
      },
      use_scm_version=True)
