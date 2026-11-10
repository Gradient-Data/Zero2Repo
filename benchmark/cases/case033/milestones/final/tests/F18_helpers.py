# feature: F18
"""Independent finite-hypothesis oracle for association probabilities."""
from itertools import product
import numpy as np
from scipy.special import logsumexp
from F01_helpers import assert_close


def association_law(existence, assignment, persistent=False, feasible=None):
    existence, assignment = np.asarray(existence), np.asarray(assignment)
    objects = len(existence)
    shape = assignment.shape[:-1]
    records, scores = [], []
    for present in product((0, 1), repeat=objects):
        for labels in product(range(objects + 1), repeat=int(np.prod(shape))):
            labels = np.array(labels).reshape(shape)
            if any(not present[k] for k in labels.flat if k < objects):
                continue
            if feasible is not None and any(not feasible[index + (int(labels[index]),)]
                                            for index in np.ndindex(shape)
                                            if labels[index] < objects):
                continue
            if persistent and any(len([k for k in row if k < objects]) !=
                                  len(set(k for k in row if k < objects)) for row in labels):
                continue
            score = np.dot(present, existence)
            score += sum(assignment[index + (int(labels[index]),)]
                         for index in np.ndindex(shape) if labels[index] < objects)
            scores.append(score)
            records.append((np.array(present), labels))
    weights = np.exp(np.array(scores) - logsumexp(scores))
    exist = np.zeros(objects)
    assign = np.zeros(shape + (objects + 1,))
    for weight, (present, labels) in zip(weights, records):
        exist += weight * present
        for index in np.ndindex(shape):
            assign[index + (int(labels[index]),)] += weight
    return exist, assign


def check_association(result, expected):
    assert_close(result.exists_dist.probs, expected[0])
    assert_close(result.assign_dist.probs, expected[1])


def check_probabilities(result, objects, detection_shape):
    exist, assign = result.exists_dist.probs, result.assign_dist.probs
    assert exist.shape == (objects,)
    assert assign.shape == detection_shape + (objects + 1,)
    for probabilities in (exist, assign):
        assert bool(probabilities.isfinite().all())
        # Marginal sums can cross an endpoint by floating-point roundoff.
        # Use the same numerical precision as the independent law checks.
        assert_close(probabilities, probabilities.clamp(0, 1).detach().cpu().numpy())
    assert_close(assign.sum(-1), np.ones(detection_shape))
