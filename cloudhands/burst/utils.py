#!/usr/bin/env python
# encoding: UTF-8

def find_xpath(xpath, tree, **kwargs):
    elements = tree.findall(xpath)
    if not kwargs:
        return elements
    else:
        query = set(kwargs.items())
        return [i for i in elements if query.issubset(set(i.attrib.items()))]

