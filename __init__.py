"""IFC 5 (.ifcx) → RDF (Turtle) converter with layer-level provenance.

Phase 1: Loader — reads JSON input and aggregates primary layers per path.
Phase 2: RDF conversion — transforms aggregated prims into an RDF graph with triple-level provenance using (ifcx:fromLayer, ifcx:layerIndex).

Multiple input files are supported; their order defines the composition order.
For each file, a layer IRI is derived from the SHA-256 hash of the raw bytes.
Value and structural triples are annotated, while auxiliary triples (owl:NamedIndividual, internal blank node structures) are excluded from annotation.
"""

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from pyoxigraph import (
    BlankNode,
    Store,
    DefaultGraph,
    Literal,
    NamedNode,
    Quad,
    RdfFormat,
    serialize
)
from Ifc5toRDF.Namespaces import (
    EX,
    IFCX,
    BSI_PROP,
    BSI_PRES,
    USD,
    RDF,
    RDFS,
    OWL,
    DCTERMS,
    XSD,
    COMPOSITION_IRI,
    RDF_JSON
)

VISUALISATION_MODE = False

# Prefixes for Turtle serialization
PREFIXES = {
    "ex": str(EX),
    "ifcx": str(IFCX),
    "bsiprop": str(BSI_PROP),
    "bsipres": str(BSI_PRES),
    "usd": str(USD),
    "rdf": str(RDF),
    "rdfs": str(RDFS),
    "owl": str(OWL),
    "dcterms": str(DCTERMS),
    "xsd": str(XSD),
}

def load_ifcx(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)

def aggregate_prims(data_entries):
    prims = defaultdict(lambda: {"path": None, "attributes": {}, "children": {}, "inherits": {}})

    for entry in data_entries:
        path = entry["path"]
        prim = prims[path]
        prim["path"] = path

        for section in ("attributes", "children", "inherits"):
            if section in entry:
                _merge_section(prim[section], entry[section], path, section)

    return dict(prims)

def _merge_section(target, incoming, path, section):
    for key, value in incoming.items():
        if key in target and target[key] != value:
            print(f"conflict in {section} for {path}: '{key}' will be overwritten")
        target[key] = value

def build_document(raw_content):
    return {
        "header": raw_content.get("header", {}),
        "imports": raw_content.get("imports", []),
        "schemas": raw_content.get("schemas", {}),
        "prims": aggregate_prims(raw_content.get("data", [])),
    }

def prim_iri(uuid):
    return EX[uuid]

def layer_iri(content_hash):
    return EX[f"layer/sha256/{content_hash}"]

def compute_hash(file_path):
    with open(file_path, "rb") as path:
        return hashlib.sha256(path.read()).hexdigest()

def to_rdf(layers_to_compute):
    """Layers: list of (doc, index, content_hash, source_name)."""
    store = Store()
    g = DefaultGraph()

    _add_composition(store, g, layers_to_compute) # adds information about the composition of multiple ifcx files to the graph. Example: <https://example.org/ifc5/hello-wall#composition> <https://example.org/ifc5/vocab#hasLayer> <https://example.org/ifc5/hello-wall#layer/sha256/a3fee878389631a279855ecfeddeb91000dce223dd955137a0c9d200ad167c60>

    for document, i, content_hash, source_name in layers_to_compute:
        ln = layer_iri(content_hash)
        _add_layer(store, g, ln, document, i, source_name)
        # adds data to store
        for prim in document["prims"].values():
            _add_prim(store, g, prim, ln, i)
    return store

def _add_composition(store, g, composition_layers):
    store.add(Quad(COMPOSITION_IRI, RDF.type, IFCX.Composition, g))
    for document, idx, content_hash, source_name in composition_layers:
        store.add(Quad(COMPOSITION_IRI, IFCX.hasLayer, layer_iri(content_hash), g))

def _add_layer(store, g, ln, document, index, source_name):
    store.add(Quad(ln, RDF.type, IFCX.Layer, g))
    store.add(Quad(ln, RDF.type, OWL.Ontology, g))
    store.add(Quad(ln, IFCX.layerIndex, Literal(str(index), datatype=XSD.integer), g))
    store.add(Quad(ln, DCTERMS.source, Literal(source_name), g))

    header = document.get("header", {})
    header_mapping = {
        "id": DCTERMS.identifier,
        "author": DCTERMS.creator,
        "timestamp": DCTERMS.created,
        "ifcxVersion": IFCX.ifcxVersion,
        "dataVersion": OWL.versionInfo,
    }
    for key, predicate in header_mapping.items():
        if key in header:
            store.add(Quad(ln, predicate, Literal(header[key]), g))

    for imp in document.get("imports", []):
        if isinstance(imp, dict) and "uri" in imp:
            store.add(Quad(ln, OWL.imports, NamedNode(imp["uri"]), g))

    for name, definition in document.get("schemas", {}).items():
        node = BlankNode()
        store.add(Quad(ln, IFCX.declaresSchema, node, g))
        store.add(Quad(node, IFCX.schemaName, Literal(name), g))
        store.add(Quad(node, IFCX.schemaDefinition, Literal(json.dumps(definition), datatype=RDF_JSON), g))

def _add_prim(store, g, prim, layer_node, layer_index):
    subject = prim_iri(prim["path"])
    store.add(Quad(subject, RDF.type, OWL.NamedIndividual, g))

    for key, value in prim["attributes"].items():
        for triple in _attribute_triples(subject, key, value):
            _add_annotated(store, g, triple, layer_node, layer_index)

    # Adds information about child objects using reification and annotations
    for name, target_uuid in prim["children"].items():
        node = BlankNode()
        _add_annotated(store, g, (subject, IFCX.hasChild, node), layer_node, layer_index)
        store.add(Quad(node, IFCX.childName, Literal(name), g))
        store.add(Quad(node, IFCX.child, prim_iri(target_uuid), g))

    # Adds information about inheritance with reification and annotations
    for slot, target_uuid in prim["inherits"].items():
        node = BlankNode()
        _add_annotated(store, g, (subject, IFCX.inherits, node), layer_node, layer_index)
        store.add(Quad(node, IFCX.slotName, Literal(slot), g))
        store.add(Quad(node, IFCX.target, prim_iri(target_uuid), g))

def _attribute_triples(subject, key, value):
    """Converts a key–value attribute pair into one or more RDF triples by applying a set of domain-specific mapping rules for different IFC/BSI/USDC data patterns, using the subject as the RDF subject and selecting predicates and object conversions based on the key structure and value content."""

    if key == "bsi::ifc::class" and isinstance(value, dict) and "uri" in value:
        triples = [(subject, RDF.type, NamedNode(value["uri"]))]
        if "code" in value:
            triples.append((subject, RDFS.label, Literal(value["code"])))
        return triples

    if key == "nlsfb::class" and isinstance(value, dict) and "uri" in value:
        return [(subject, IFCX.classification, NamedNode(value["uri"]))]

    if key == "bsi::ifc::material" and isinstance(value, dict) and "uri" in value:
        return [(subject, IFCX.hasMaterial, NamedNode(value["uri"]))]

    if key == "bsi::ifc::spaceBoundary" and isinstance(value, dict):
        triples = []
        rel_space = value.get("relatingspace")
        rel_elem = value.get("relatedelement")
        if isinstance(rel_space, dict) and "ref" in rel_space:
            triples.append((subject, IFCX.relatingSpace, prim_iri(rel_space["ref"])))
        if isinstance(rel_elem, dict) and "ref" in rel_elem:
            triples.append((subject, IFCX.relatedElement, prim_iri(rel_elem["ref"])))
        return triples

    # TODO: What happens to other custom data?
    if key == "customdata" and isinstance(value, dict) and "originalStepInstance" in value:
        return [(subject, IFCX.originalStepInstance, Literal(value["originalStepInstance"]))]

    if key.startswith("bsi::ifc::prop::"):
        local = key.rsplit("::", 1)[-1]
        return [(subject, BSI_PROP[local], _to_literal(value))]

    if key.startswith("bsi::ifc::presentation::"):
        local = key.rsplit("::", 1)[-1]
        return [(subject, BSI_PRES[local], _to_literal(value))]

    if key.startswith("usd::"):
        local = key.replace("::", "_")
        content = "..." if VISUALISATION_MODE else json.dumps(value)
        return [(subject, USD[local], Literal(content, datatype=RDF_JSON))]

    local = key.replace("::", "_")
    return [(subject, IFCX[local], _to_literal(value))]

def _add_annotated(store, g, triple, layer_node, layer_index):
    """Adds main assertion + standard reification (rdf:Statement / rdf:subject / rdf:predicate / rdf:object) with layer annotations."""
    sub, pre, obj = triple
    store.add(Quad(sub, pre, obj, g)) # stores main triple

    reifier = BlankNode()
    # storing reification
    store.add(Quad(reifier, RDF.type, RDF.Statement, g))
    store.add(Quad(reifier, RDF.subject, sub, g))
    store.add(Quad(reifier, RDF.predicate, pre, g))
    store.add(Quad(reifier, RDF.object, obj, g))

    # storing layer annotations
    store.add(Quad(reifier, IFCX.fromLayer, layer_node, g))
    store.add(Quad(reifier, IFCX.layerIndex, Literal(str(layer_index), datatype=XSD.integer), g))

def _to_literal(value):
    """Converts a Python value into an RDF Literal and assigns an appropriate XSD datatype based on the value's type, falling back to JSON-encoded RDF when necessary."""
    if isinstance(value, bool):
        return Literal(str(value).lower(), datatype=XSD.boolean)
    if isinstance(value, int):
        return Literal(str(value), datatype=XSD.integer)
    if isinstance(value, float):
        return Literal(str(value), datatype=XSD.decimal)
    if isinstance(value, str):
        return Literal(value)
    return Literal(json.dumps(value), datatype=RDF_JSON)

if __name__ == "__main__":
    print("Ifc5toRDF\n\n")
    args = sys.argv[1:]
    if not args:
        args = [str(Path(__file__).parent / "files" / "hello-wall.ifcx")]

    layers = []
    for i, arg in enumerate(args):
        p = Path(arg)
        raw = load_ifcx(p)
        doc = build_document(raw)
        h = compute_hash(p)
        layers.append((doc, i, h, p.name))

    ds = to_rdf(layers)

    ttl_path = Path(args[0]).with_suffix(".ttl")
    with open(ttl_path, "wb") as f:
        serialize(ds, f, format=RdfFormat.TURTLE, prefixes=PREFIXES)

    print(f"\nRDF: {len(ds)} quads written to {ttl_path}")
