from argparse import ArgumentParser
from .vanecore import Vane

from os.path import join, dirname

parser = ArgumentParser(description="vane 2.0")
parser.add_argument("action")
parser.add_argument("--url", dest="url")
parser.add_argument("--import_path", dest="database_path")
args = parser.parse_args()

vane = Vane()
vane.perfom_action(**vars(args))