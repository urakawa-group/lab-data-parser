"""Naming conventions: map the many spellings setups use onto one canonical name (species for now)."""

import lab_data_parser.naming.species as species
from lab_data_parser.naming.species import SpeciesConvention, get_convention, rename_species

__all__ = ["species", "SpeciesConvention", "get_convention", "rename_species"]
