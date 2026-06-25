# IFC5-to-RDF

Convert **IFC 5 files** (`.ifcx`, JSON) into **RDF/Turtle** while preserving layer provenance.

## Overview

IFC 5 is layer-based: multiple `.ifcx` files are composed on top of each other, where later layers can override values from earlier ones. This project reads the input files in composition order, aggregates the prims per `path`, and writes out an RDF graph. Every domain statement is reified (`rdf:Statement` with `rdf:subject` / `rdf:predicate` / `rdf:object`), so that `ifcx:fromLayer` and `ifcx:layerIndex` record which layer each statement originated from.

## Usage

```bash
# Single file → files/hello-wall.ttl
python init.py files/hello-wall.ifcx

# Multiple layers in composition order
python init.py files/hello-wall.ifcx files/hello-wall-add-fire-rating-60.ifcx
```
The Turtle output is written next to the first input file (.ttl) and uses namespace prefixes (ifcx:, bsiprop:, rdf: …) for compact IRIs.
