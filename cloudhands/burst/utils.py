#!/usr/bin/env python
# encoding: UTF-8

import xml.sax.saxutils

def find_xpath(xpath, tree, namespaces={}, **kwargs):
    elements = tree.iterfind(xpath, namespaces=namespaces)
    if not kwargs:
        return elements
    else:
        query = set(kwargs.items())
        return (i for i in elements if query.issubset(set(i.attrib.items())))

def unescape_script(text):
    return xml.sax.saxutils.unescape(
        text, entities={
            "&quot;": '"', "&#13;": "\n", "&#37;": "%", "&apos;": "'"})
