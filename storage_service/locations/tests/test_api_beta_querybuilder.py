# -*- coding: utf8 -*-
"""Tests for the querybuilder module."""

from __future__ import print_function
from datetime import datetime

from django.db.models import Q

from locations.models import Package, File
from locations.api.beta.remple import QueryBuilder


def test_query_expression_construction_dates():
    qb = QueryBuilder(File, primary_key='uuid')
    FILTER_1 = ['ingestion_time', '<=', '2015-12-17T11:59:59']
    qe = qb.get_query_expression(FILTER_1)
    filter_obj = qe.children[0]
    assert qb.errors == {}
    assert isinstance(qe, Q)
    assert qe.connector == 'AND'
    assert len(qe.children) == 1
    assert filter_obj[0] == 'ingestion_time__lte'
    assert isinstance(filter_obj[1], datetime)
    FILTER_2 = [
        'and', [['pronom_id', '=', 'fmt/19'],
                ['ingestion_time', '<=', '2015-12-17T11:59:59'],
                ['ingestion_time', '>=', '2015-12-16T00:00:01']]]
    qe = qb.get_query_expression(FILTER_2)
    assert qe.connector == 'AND'
    assert isinstance(qe, Q)
    assert qb.errors == {}
    assert len(qe.children) == 3


def test_query_expression_construction():
    """Test that the ``get_query_expression`` method can convert Python lists
    to the corresponding Django Q expression.
    """
    qb = QueryBuilder(Package, primary_key='uuid')
    assert qb.model_name == 'Package'

    FILTER_1 = ['description', 'like', '%a%']
    qe = qb.get_query_expression(FILTER_1)
    filter_obj = qe.children[0]
    assert qb.errors == {}
    assert isinstance(qe, Q)
    assert qe.connector == 'AND'
    assert len(qe.children) == 1
    assert filter_obj[0] == 'description__contains'
    assert filter_obj[1] == '%a%'

    FILTER_2 = ['origin_pipeline', 'description', 'regex', '^[JS]']
    qe = qb.get_query_expression(FILTER_2)
    filter_obj = qe.children[0]
    assert qb.errors == {}
    assert qe.connector == 'AND'
    assert len(qe.children) == 1
    assert filter_obj[0] == 'origin_pipeline__description__regex'
    assert filter_obj[1] == '^[JS]'

    FILTER_3A = ['origin_pipeline', '=', None]
    qe = qb.get_query_expression(FILTER_3A)
    filter_obj = qe.children[0]
    assert qb.errors == {}
    assert qe.connector == 'AND'
    assert len(qe.children) == 1
    assert filter_obj[0] == 'origin_pipeline__isnull'
    assert filter_obj[1] is True

    FILTER_3B = ['origin_pipeline', '!=', None]
    qe = qb.get_query_expression(FILTER_3B)
    filter_obj = qe.children[0]
    assert qb.errors == {}
    assert qe.connector == 'AND'
    assert len(qe.children) == 1
    assert filter_obj[0] == 'origin_pipeline__isnull'
    assert filter_obj[1] is False

    UUID_1 = '75a481ea-6e56-4800-81b2-6679d1e8f5ea'
    UUID_2 = '90bd9d01-22f5-447c-8b4b-15578c6b8f37'
    FILTER_4 = ['replicas', 'uuid', 'in', [UUID_1, UUID_2]]
    qe = qb.get_query_expression(FILTER_4)
    filter_obj = qe.children[0]
    assert qb.errors == {}
    assert qe.connector == 'AND'
    assert len(qe.children) == 1
    assert filter_obj[0] == 'replicas__uuid__in'
    assert sorted(filter_obj[1]) == sorted([UUID_1, UUID_2])

    FILTER_5 = ['not', ['description', 'like', '%a%']]
    qe = qb.get_query_expression(FILTER_5)
    filter_obj = qe.children[0]
    assert qb.errors == {}
    assert qe.negated is True
    assert qe.connector == 'AND'
    assert len(qe.children) == 1
    assert filter_obj[0] == 'description__contains'
    assert filter_obj[1] == '%a%'

    FILTER_6 = ['and', [['description', 'like', '%a%'],
                        ['origin_pipeline', 'description', '=',
                         'Well described.']]]
    qe = qb.get_query_expression(FILTER_6)
    assert qb.errors == {}
    filter_obj_1 = qe.children[0]
    filter_obj_2 = qe.children[1]
    assert len(qe.children) == 2
    assert qe.negated is False
    assert qe.connector == 'AND'
    assert filter_obj_1[0] == 'description__contains'
    assert filter_obj_1[1] == '%a%'
    assert filter_obj_2[0] == 'origin_pipeline__description__exact'
    assert filter_obj_2[1] == 'Well described.'

    FILTER_7 = ['or', [['description', 'like', '%a%'],
                       ['origin_pipeline', 'description', '=',
                        'Well described.']]]
    qe = qb.get_query_expression(FILTER_7)
    assert qb.errors == {}
    filter_obj_1 = qe.children[0]
    filter_obj_2 = qe.children[1]
    assert len(qe.children) == 2
    assert qe.negated is False
    assert qe.connector == 'OR'
    assert filter_obj_1[0] == 'description__contains'
    assert filter_obj_1[1] == '%a%'
    assert filter_obj_2[0] == 'origin_pipeline__description__exact'
    assert filter_obj_2[1] == 'Well described.'

    FILTER_8 = ['and', [['description', 'like', '%a%'],
                        ['not', ['description', 'like', 'T%']],
                        ['or', [['size', '<', 1000],
                                ['size', '>', 512]]]]]
    qe = qb.get_query_expression(FILTER_8)
    assert qb.errors == {}
    filter_obj_1 = qe.children[0]
    filter_obj_2 = qe.children[1]
    filter_obj_3 = qe.children[2]
    assert len(qe.children) == 3
    assert qe.negated is False
    assert qe.connector == 'AND'
    assert filter_obj_1[0] == 'description__contains'
    assert filter_obj_1[1] == '%a%'
    assert filter_obj_2.negated is True
    assert filter_obj_2.children[0][0] == 'description__contains'
    assert filter_obj_2.children[0][1] == 'T%'
    assert filter_obj_3.negated is False
    assert filter_obj_3.connector == 'OR'
    assert len(filter_obj_3.children) == 2
    subchild_1 = filter_obj_3.children[0]
    subchild_2 = filter_obj_3.children[1]
    assert subchild_1[0] == 'size__lt'
    assert subchild_1[1] == 1000
    assert subchild_2[0] == 'size__gt'
    assert subchild_2[1] == 512

    qb.clear_errors()

    BAD_FILTER_1 = ['gonzo', 'like', '%a%']
    qe = qb.get_query_expression(BAD_FILTER_1)
    assert qe is None
    assert qb.errors['Package.gonzo'] == (
        'Searching on Package.gonzo is not permitted')
    assert qb.errors['Malformed query error'] == (
        'The submitted query was malformed')

    qb.clear_errors()

    BAD_FILTER_2 = ['origin_pipeline', '<', 2]
    qe = qb.get_query_expression(BAD_FILTER_2)
    # Note: ``qe`` will be the nonsensical
    # ``(AND: ('origin_pipeline__None', 2))`` here. This is ok, since the
    # public method ``get_query_set`` will raise an error before executing this
    # query against the db.
    assert qb.errors['Package.origin_pipeline.<'] == (
        'The relation < is not permitted for Package.origin_pipeline')


def test_order_by_expression_construction():
    """Test that the ``get_order_bys`` method can convert Python lists of lists
    to a list of strings that the Django ORM's ``order_by`` method can use to
    creat an SQL ``ORDER BY`` clause.
    """

    qb = QueryBuilder(Package)
    assert qb.model_name == 'Package'
    assert qb.primary_key == 'uuid'

    ORDER_BYS_1 = [['description']]
    order_bys = qb.get_order_bys(ORDER_BYS_1)
    assert order_bys == ['description']

    ORDER_BYS_2 = [['description', 'desc']]
    order_bys = qb.get_order_bys(ORDER_BYS_2)
    assert order_bys == ['-description']

    ORDER_BYS_3 = [['origin_pipeline', 'uuid', 'desc']]
    order_bys = qb.get_order_bys(ORDER_BYS_3)
    assert order_bys == ['-origin_pipeline__uuid']

    ORDER_BYS_4 = [['origin_pipeline', 'uuid', 'asc']]
    order_bys = qb.get_order_bys(ORDER_BYS_4)
    assert order_bys == ['origin_pipeline__uuid']

    ORDER_BYS_5 = [['origin_pipeline', 'monkey', 'asc']]
    order_bys = qb.get_order_bys(ORDER_BYS_5)
    assert qb.errors['Pipeline.monkey'] == (
        'Searching on Pipeline.monkey is not permitted')

    ORDER_BYS_6 = [['origin_pipeline', 'uuid', 'asc'], ['description', 'desc']]
    order_bys = qb.get_order_bys(ORDER_BYS_6)
    assert order_bys == ['origin_pipeline__uuid', '-description']


def test_query_dict_expression_construction():
    """Test that the ``get_query_expression`` method can convert Python dicts
    to the corresponding Django Q expression.
    """
    qb = QueryBuilder(Package, primary_key='uuid')
    assert qb.model_name == 'Package'

    FILTER_1 = {'attribute': 'description', 'relation': 'like', 'value': '%a%'}
    qe = qb.get_query_expression(FILTER_1)
    filter_obj = qe.children[0]
    assert qb.errors == {}
    assert isinstance(qe, Q)
    assert qe.connector == 'AND'
    assert len(qe.children) == 1
    assert filter_obj[0] == 'description__contains'
    assert filter_obj[1] == '%a%'

    FILTER_2 = {'attribute': 'origin_pipeline',
                'subattribute': 'description',
                'relation': 'regex',
                'value': '^[JS]'}
    qe = qb.get_query_expression(FILTER_2)
    filter_obj = qe.children[0]
    assert qb.errors == {}
    assert qe.connector == 'AND'
    assert len(qe.children) == 1
    assert filter_obj[0] == 'origin_pipeline__description__regex'
    assert filter_obj[1] == '^[JS]'

    FILTER_3A = {'attribute': 'origin_pipeline', 'relation': '=', 'value': None}
    qe = qb.get_query_expression(FILTER_3A)
    filter_obj = qe.children[0]
    assert qb.errors == {}
    assert qe.connector == 'AND'
    assert len(qe.children) == 1
    assert filter_obj[0] == 'origin_pipeline__isnull'
    assert filter_obj[1] is True

    FILTER_3B = {'attribute': 'origin_pipeline', 'relation': '!=',
                 'value': None}
    qe = qb.get_query_expression(FILTER_3B)
    filter_obj = qe.children[0]
    assert qb.errors == {}
    assert qe.connector == 'AND'
    assert len(qe.children) == 1
    assert filter_obj[0] == 'origin_pipeline__isnull'
    assert filter_obj[1] is False

    UUID_1 = '75a481ea-6e56-4800-81b2-6679d1e8f5ea'
    UUID_2 = '90bd9d01-22f5-447c-8b4b-15578c6b8f37'
    FILTER_4 = {'attribute': 'replicas',
                'subattribute': 'uuid',
                'relation': 'in',
                'value': [UUID_1, UUID_2]}
    qe = qb.get_query_expression(FILTER_4)
    filter_obj = qe.children[0]
    assert qb.errors == {}
    assert qe.connector == 'AND'
    assert len(qe.children) == 1
    assert filter_obj[0] == 'replicas__uuid__in'
    assert sorted(filter_obj[1]) == sorted([UUID_1, UUID_2])

    FILTER_5 = {'negation': 'not',
                'complement': {'attribute': 'description',
                               'relation': 'like',
                               'value': '%a%'}}
    qe = qb.get_query_expression(FILTER_5)
    filter_obj = qe.children[0]
    assert qb.errors == {}
    assert qe.negated is True
    assert qe.connector == 'AND'
    assert len(qe.children) == 1
    assert filter_obj[0] == 'description__contains'
    assert filter_obj[1] == '%a%'

    FILTER_6 = {'conjunction': 'and',
                'complement': [{'attribute': 'description',
                                'relation': 'like',
                                'value': '%a%'},
                               {'attribute': 'origin_pipeline',
                                'subattribute': 'description',
                                'relation': '=',
                                'value': 'Well described.'}]}
    qe = qb.get_query_expression(FILTER_6)
    assert qb.errors == {}
    filter_obj_1 = qe.children[0]
    filter_obj_2 = qe.children[1]
    assert len(qe.children) == 2
    assert qe.negated is False
    assert qe.connector == 'AND'
    assert filter_obj_1[0] == 'description__contains'
    assert filter_obj_1[1] == '%a%'
    assert filter_obj_2[0] == 'origin_pipeline__description__exact'
    assert filter_obj_2[1] == 'Well described.'

    FILTER_7 = {'conjunction': 'or',
                'complement': [{'attribute': 'description',
                                'relation': 'like',
                                'value': '%a%'},
                               {'attribute': 'origin_pipeline',
                                'subattribute': 'description',
                                'relation': '=',
                                'value': 'Well described.'}]}
    qe = qb.get_query_expression(FILTER_7)
    assert qb.errors == {}
    filter_obj_1 = qe.children[0]
    filter_obj_2 = qe.children[1]
    assert len(qe.children) == 2
    assert qe.negated is False
    assert qe.connector == 'OR'
    assert filter_obj_1[0] == 'description__contains'
    assert filter_obj_1[1] == '%a%'
    assert filter_obj_2[0] == 'origin_pipeline__description__exact'
    assert filter_obj_2[1] == 'Well described.'

    FILTER_8 = {'conjunction': 'and',
                'complement': [{'attribute': 'description',
                                'relation': 'like',
                                'value': '%a%'},
                               {'negation': 'not',
                                'complement': {'attribute': 'description',
                                               'relation': 'like',
                                               'value': 'T%'}},
                               {'conjunction': 'or',
                                'complement': [{'attribute': 'size',
                                                'relation': '<',
                                                'value': 1000},
                                               {'attribute': 'size',
                                                'relation': '>',
                                                'value': 512}]}]}
    qe = qb.get_query_expression(FILTER_8)
    assert qb.errors == {}
    filter_obj_1 = qe.children[0]
    filter_obj_2 = qe.children[1]
    filter_obj_3 = qe.children[2]
    assert len(qe.children) == 3
    assert qe.negated is False
    assert qe.connector == 'AND'
    assert filter_obj_1[0] == 'description__contains'
    assert filter_obj_1[1] == '%a%'
    assert filter_obj_2.negated is True
    assert filter_obj_2.children[0][0] == 'description__contains'
    assert filter_obj_2.children[0][1] == 'T%'
    assert filter_obj_3.negated is False
    assert filter_obj_3.connector == 'OR'
    assert len(filter_obj_3.children) == 2
    subchild_1 = filter_obj_3.children[0]
    subchild_2 = filter_obj_3.children[1]
    assert subchild_1[0] == 'size__lt'
    assert subchild_1[1] == 1000
    assert subchild_2[0] == 'size__gt'
    assert subchild_2[1] == 512

    qb.clear_errors()

    BAD_FILTER_1 = {'attribute': 'gonzo', 'relation': 'like', 'value': '%a%'}
    qe = qb.get_query_expression(BAD_FILTER_1)
    assert qe is None
    assert qb.errors['Package.gonzo'] == (
        'Searching on Package.gonzo is not permitted')
    assert qb.errors['Malformed query error'] == (
        'The submitted query was malformed')

    qb.clear_errors()

    BAD_FILTER_2 = {'attribute': 'origin_pipeline', 'relation': '<', 'value': 2}
    qe = qb.get_query_expression(BAD_FILTER_2)
    # Note: ``qe`` will be the nonsensical
    # ``(AND: ('origin_pipeline__None', 2))`` here. This is ok, since the
    # public method ``get_query_set`` will raise an error before executing this
    # query against the db.
    assert qb.errors['Package.origin_pipeline.<'] == (
        'The relation < is not permitted for Package.origin_pipeline')
