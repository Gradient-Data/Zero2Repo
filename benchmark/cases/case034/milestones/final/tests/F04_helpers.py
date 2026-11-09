# feature: F04
"""Real nonlinear network simulation shared by loop acceptance arms."""

import velunex as ct


def simulate_square_network(loop):
    """Construct and consume a response on the public simulation path."""
    system = ct.nlsys(None, lambda t, x, u, p: [u[0]**2 + 1],
                      inputs='u', outputs='y', name='square')
    net = ct.interconnect(
        [system], connections=[['square.u', 'square.y']] if loop else False,
        inplist=['square.u'], outlist=['square.y'])
    return ct.input_output_response(net, [0, 1, 2], [1, 2, 3], squeeze=False)
