# feature: F04
"""Restartable source and explicit column-group expectations."""
from itertools import count

from velnora import Dataset, IterableDataset


def produce_records(records):
    yield from records


def endless_records():
    for number in count():
        yield {'number': number, 'text': str(number)}


def iterable_records(records):
    # Lists in generator kwargs denote independently reorderable source shards.
    # A tuple keeps these records together as one restartable source.
    return IterableDataset.from_generator(produce_records, gen_kwargs={'records': tuple(records)})


def finite_and_iterable(records):
    return (Dataset.from_list(records), iterable_records(records))


def group_columns(records):
    return {name: [row[name] for row in records] for name in records[0]}
