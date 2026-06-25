from pyoxigraph import NamedNode
from Ifc5toRDF.NS import NS

EX = NS("https://example.org/ifc5/hello-wall#")
IFCX = NS("https://example.org/ifc5/vocab#")
BSI_PROP = NS("https://example.org/bsi/ifc/prop#")
BSI_PRES = NS("https://example.org/bsi/ifc/presentation#")
USD = NS("https://example.org/usd#")
RDF = NS("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = NS("http://www.w3.org/2000/01/rdf-schema#")
OWL = NS("http://www.w3.org/2002/07/owl#")
DCTERMS = NS("http://purl.org/dc/terms/")
XSD = NS("http://www.w3.org/2001/XMLSchema#")

COMPOSITION_IRI = EX["composition"]
RDF_JSON = NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#JSON")