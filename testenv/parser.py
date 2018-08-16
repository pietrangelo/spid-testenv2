# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import zlib
from base64 import b64decode
from collections import namedtuple
from datetime import datetime, timedelta

from flask import escape
from lxml import etree, objectify

from testenv.exceptions import (DeserializationError, RequestParserError,
                                StopValidation, ValidationError,
                                XMLFormatValidationError)


HTTPRedirectRequest = namedtuple(
    'HTTPRedirectRequest',
    ['saml_request', 'sig_alg', 'signature'],
)


HTTPPostRequest = namedtuple('HTTPPostRequest', ['saml_request'])


class HTTPRedirectRequestParser(object):
    def __init__(self, querystring, request_class=None):
        self._querystring = querystring
        self._request_class = request_class or HTTPRedirectRequest
        self._saml_request = None
        self._sig_alg = None
        self._signature = None

    def parse(self):
        self._saml_request = self._parse_saml_request()
        self._sig_alg = self._parse_sig_alg()
        self._signature = self._parse_signature()
        return self._build_request()

    def _parse_saml_request(self):
        saml_request = self._extract('SAMLRequest')
        return self._decode_saml_request(saml_request)

    def _extract(self, key):
        try:
            return self._querystring[key]
        except KeyError as e:
            self._fail("Dato mancante nella request: '{}'".format(e.args[0]))

    @staticmethod
    def _fail(message):
        raise RequestParserError(message)

    def _decode_saml_request(self, saml_request):
        try:
            return self._convert_saml_request(saml_request)
        except Exception:  # FIXME detail exceptions
            self._fail("Impossibile decodificare l'elemento 'SAMLRequest'")

    @staticmethod
    def _convert_saml_request(saml_request):
        saml_request = b64decode(saml_request)
        saml_request = zlib.decompress(saml_request, -15)
        return saml_request.decode()

    def _parse_sig_alg(self):
        return self._extract('SigAlg')

    def _parse_signature(self):
        signature = self._extract('Signature')
        return self._decode_signature(signature)

    def _decode_signature(self, signature):
        try:
            return b64decode(signature)
        except Exception:
            self._fail("Impossibile decodificare l'elemento 'Signature'")

    def _build_request(self):
        return self._request_class(
            self._saml_request,
            self._sig_alg,
            self._signature,
        )


class HTTPPostRequestParser(object):
    def __init__(self, form, request_class=None):
        self._form = form
        self._request_class = request_class or HTTPPostRequest
        self._saml_request = None

    def parse(self):
        self._saml_request = self._parse_saml_request()
        return self._build_request()

    def _parse_saml_request(self):
        saml_request = self._extract('SAMLRequest')
        return self._decode_saml_request(saml_request)

    def _extract(self, key):
        try:
            return self._form[key]
        except KeyError as e:
            self._fail("Dato mancante nella request: '{}'".format(e.args[0]))

    @staticmethod
    def _fail(message):
        raise RequestParserError(message)

    def _decode_saml_request(self, saml_request):
        try:
            return self._convert_saml_request(saml_request)
        except Exception:  # FIXME detail exceptions
            self._fail("Impossibile decodificare l'elemento 'SAMLRequest'")

    @staticmethod
    def _convert_saml_request(saml_request):
        saml_request = b64decode(saml_request)
        return saml_request.decode()

    def _build_request(self):
        return self._request_class(self._saml_request)


class HTTPRequestDeserializer(object):
    _validators = []

    def __init__(self, request, saml_class=None):
        self._request = request
        self._saml_class = saml_class or SAMLTree
        self._validation_errors = []

    def deserialize(self):
        self._validate()
        if self._validation_errors:
            raise DeserializationError(self._validation_errors)
        return self._deserialize()

    def _validate(self):
        try:
            self._run_validators()
        except StopValidation:
            pass

    def _run_validators(self):
        for validator in self._validators:
            self._run_validator(validator)

    def _run_validator(self, validator):
        try:
            validator.validate(self._request)
        except XMLFormatValidationError as e:
            self._handle_blocking_error(e)
        except ValidationError as e:
            self._handle_nonblocking_error(e)

    def _handle_blocking_error(self, error):
        self._handle_nonblocking_error(error)
        raise StopValidation

    def _handle_nonblocking_error(self, error):
        self._validation_errors += error.details

    def _deserialize(self):
        xml_doc = objectify.fromstring(self._request.saml_request)
        return self._saml_class(xml_doc)


class SAMLTree(object):
    def __init__(self, xml_doc):
        self._xml_doc = xml_doc
        self._bind_tag()
        self._bind_attributes()
        self._bind_text()
        self._bind_subtrees()

    def _bind_tag(self):
        self.tag = etree.QName(self._xml_doc).localname

    def _bind_attributes(self):
        for attr_name, attr_val in self._xml_doc.attrib.items():
            setattr(self, attr_name.lower(), attr_val)

    def _bind_text(self):
        self.text = self._xml_doc.text

    def _bind_subtrees(self):
        for child in self._xml_doc.iterchildren():
            child_name = etree.QName(child).localname.lower()
            subtree = SAMLTree(child)
            setattr(self, child_name, subtree)
