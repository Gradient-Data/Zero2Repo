# feature: F20
"""Acceptance evidence for biological sequence ingestion and probability models."""
import numpy as np
import torch
import velnora
from scipy import stats
from velnora import poutine
from velnora.contrib.mue.dataloaders import BiosequenceDataset, write
from velnora.contrib.mue.missingdatahmm import MissingDataDiscreteHMM
from velnora.contrib.mue.models import ProfileHMM, FactorMuE
from velnora.contrib.mue.statearrangers import Profile
from _helpers import invoke, isolated_state
from F01_helpers import assert_close
from F16_helpers import epidemic_cpu_threads
from F20_helpers import (fasta_sequences, hmm_enumeration, alignment_probability,
    sequence_trace, sequence_draws, normal_site, profile_components,
    fixed_evaluation, predictive_sequence_score)


def test_f20_t01(tmp_path):
    with isolated_state(dtype=torch.float64):
        for name, members in [('amino-acid', 'ARNDCQEGHILKMFPSTWYV'), ('dna', 'ACGT'), ('ACGU', 'ACGU')]:
            seqs = [members[:2]+'?'+members[2:], members[-2:]]
            path = tmp_path / 'input.fa'
            path.write_text('>first\n'+seqs[0][:3]+'\n'+seqs[0][3:]+'\n>second\n'+seqs[1]+'\n')
            for source, kind in [(seqs, 'list'), (str(path), 'fasta')]:
                for stop in (False, True):
                    ds = BiosequenceDataset(source, kind, name, include_stop=stop)
                    alphabet = list(ds.alphabet)
                    assert set(alphabet) == set(members + ('*' if stop else ''))
                    assert ds.max_length == max(map(len, seqs)) + stop
                    assert len(ds) == len(seqs)
                    for i, seq in enumerate(seqs):
                        seq += '*' if stop else ''
                        data, length = ds[i]
                        assert length == len(seq)
                        assert_close(data, ds.seq_data[i])
                        assert_close(ds.L_data[i], len(seq))
                        expected = [[float(symbol == a) for a in alphabet] for symbol in seq]
                        expected += [[0.]*len(alphabet)]*(ds.max_length-len(seq))
                        assert_close(data, expected)
            padded = BiosequenceDataset(seqs, alphabet=name, max_length=len(seqs[0])+3)
            assert padded.max_length == len(seqs[0])+3
            assert_close(padded.seq_data[:, -3:], 0.)
        default = BiosequenceDataset(['A?R', 'G'])
        assert set(default.alphabet) == set('ARNDCQEGHILKMFPSTWYV')
        assert default.max_length == 3
        assert_close(default.L_data, [3., 1.])


def test_f20_t02():
    with isolated_state(dtype=torch.float64):
        initial = np.array([.81, .19])
        transition = np.array([[.27, .73], [.62, .38]])
        emission = np.array([[.88, .12], [.21, .79]])
        hmm = MissingDataDiscreteHMM(*(torch.tensor(x).log() for x in (initial, transition, emission)))
        for symbols in ([0, None, 1, 1], [1, 0], [None, None, None]):
            data = torch.tensor([[float(s == j) for j in range(2)] for s in symbols])
            probability, smooth = hmm_enumeration(initial, transition, emission, data)
            assert_close(invoke(hmm.log_prob, data).value, np.log(probability))
            assert_close(invoke(hmm.smooth, data).value.exp(), smooth[None])
            filtered = np.stack([hmm_enumeration(initial, transition, emission, data[:t+1])[1][-1] for t in range(len(data))])
            assert_close(invoke(hmm.filter, data).value.exp(), filtered[None])


def test_f20_t03(epidemic_cpu_threads):
    # Score fresh sequences as well as training sequences; no trajectory is fixed.
    for kind in ('profile', 'Normal', 'Laplace'):
        with isolated_state(seed=20203, dtype=torch.float64):
            train = BiosequenceDataset(['AAAA', 'AAA', 'AAAAA', 'AAAA']*3, alphabet='AB', max_length=5)
            test = BiosequenceDataset(['AA', 'AAAAA'], alphabet='AB', max_length=5)
            model = ProfileHMM(4, 2) if kind == 'profile' else FactorMuE(5, 2, 2, latent_seq_length=4, substitution_matrix=False, inverse_temp_prior=1., z_prior_distribution=kind)
            # Average actual predictive evidence to reduce posterior draw noise.
            velnora.set_rng_seed(20204)
            before = np.mean([predictive_sequence_score(model, test) for _ in range(12)])
            losses = invoke(model.fit_svi, train, kwargs={'epochs':65, 'batch_size':len(train)}, timeout=180).value
            assert np.isfinite(losses).all() and len(losses) > 1
            velnora.set_rng_seed(20204)
            after = np.mean([predictive_sequence_score(model, test) for _ in range(12)])
            assert after > before, (kind, before, after)
            assert np.isfinite(invoke(model.evaluate, train, test).value).all()
            trace = sequence_trace(model, test.seq_data[:1], guide=True)
            fixed = sequence_draws(trace)
            observed = sequence_trace(model, test.seq_data, fixed)
            components = profile_components(model, fixed)
            expected = [np.log(alignment_probability(*components, row.numpy())) for row in test.seq_data]
            assert_close(observed.nodes['obs_seq']['fn'].log_prob(test.seq_data), expected)


def test_f20_t04(epidemic_cpu_threads):
    for kind in ('profile', 'Normal', 'Laplace'):
        with isolated_state(seed=204, dtype=torch.float64):
            train = BiosequenceDataset(['AB', 'AAB', 'B'], alphabet='AB')
            test = BiosequenceDataset(['BA', 'BBB'], alphabet='AB', max_length=3)
            model = ProfileHMM(2, 2) if kind == 'profile' else FactorMuE(3, 2, 2, latent_seq_length=2, inverse_temp_prior=1., z_prior_distribution=kind)
            result, expected = fixed_evaluation(model, train, test)
            assert len(result) == 4
            assert_close(torch.as_tensor(result[0]), expected[0].sum())
            assert_close(torch.as_tensor(result[1]), expected[1].sum())


def test_f20_t05(epidemic_cpu_threads):
    for kind in ('profile', 'Normal', 'Laplace'):
        with isolated_state(seed=205, dtype=torch.float64):
            train = BiosequenceDataset(['A', 'ABB', 'BA'], alphabet='AB', max_length=5)
            test = BiosequenceDataset(['BBBB', 'AB'], alphabet='AB', max_length=5)
            model = ProfileHMM(2, 2) if kind == 'profile' else FactorMuE(5, 2, 2, latent_seq_length=2, inverse_temp_prior=1., z_prior_distribution=kind)
            result, expected = fixed_evaluation(model, train, test)
            for actual, evidence, ds in zip(result[2:], expected, (train, test)):
                assert_close(torch.as_tensor(actual), np.exp(np.mean(-evidence/ds.L_data.numpy())))


def test_f20_t06(epidemic_cpu_threads):
    for family in ('Normal', 'Laplace'):
        with isolated_state(seed=206, dtype=torch.float64):
            ds = BiosequenceDataset(['AAA', 'BBB', 'AB'], alphabet='AB')
            model = FactorMuE(3, 2, 3, z_prior_distribution=family, inverse_temp_prior=1.)
            invoke(model.fit_svi, ds, kwargs={'epochs':3, 'batch_size':3}).value
            loc, scale = invoke(model.embed, ds, kwargs={'batch_size':2}).value
            assert loc.shape == scale.shape == (3, 3)
            assert torch.all(scale > 0)
            # Reordering must reorder fitted uncertainty, independent of batching.
            reverse = BiosequenceDataset(['AB', 'BBB', 'AAA'], alphabet='AB')
            rloc, rscale = model.embed(reverse, batch_size=1)
            assert_close(rloc, loc.flip(0)); assert_close(rscale, scale.flip(0))
            assert not torch.allclose(loc[0], loc[1])
            distribution = stats.norm if family == 'Normal' else stats.laplace
            for i, row in enumerate(ds.seq_data):
                guide = sequence_trace(model, row[None], guide=True)
                law = guide.nodes['latent']['fn']
                for shift in (-.7, .4):
                    point = loc[i:i+1] + shift
                    assert_close(law.log_prob(point), distribution.logpdf(point.numpy(), loc[i:i+1].numpy(), scale[i:i+1].numpy()).sum(-1))


def test_f20_t07():
    with isolated_state(dtype=torch.float64):
        assert ProfileHMM(1, 2).latent_seq_length == 1
        assert FactorMuE(2, 2, 1).z_dim == 1
        for bad in (0, -2, 1.5):
            for args in ((bad, 2), (2, bad)):
                result = invoke(ProfileHMM, *args, allowed_exceptions=(AssertionError,))
                assert isinstance(result.exception, AssertionError)
            for args, kwargs in [((bad, 2, 1), {}), ((2, bad, 1), {}), ((2, 2, bad), {}), ((2, 2, 1), {'latent_seq_length':bad})]:
                result = invoke(FactorMuE, *args, kwargs=kwargs, allowed_exceptions=(AssertionError,))
                assert isinstance(result.exception, AssertionError)


def test_f20_t08(tmp_path):
    with isolated_state(dtype=torch.float64):
        alphabet = np.array(list('BA*'))
        # Explicit category mapping and zero padding, independent of the reader.
        x = torch.tensor([[[0.,1.,0.],[1.,0.,0.],[0.,0.,1.],[0.,1.,0.],[0.,0.,1.],[1.,0.,0.],[0.,0.,0.]],
                          [[1.,0.,0.],[0.,0.,0.],[0.,0.,0.],[0.,0.,0.],[0.,0.,0.],[0.,0.,0.],[0.,0.,0.]]])
        path = tmp_path / 'output.fa'
        invoke(write, x, alphabet, str(path)).value
        assert fasta_sequences(path) == ['AB*A*B', 'B']
        invoke(write, x[:1], alphabet, str(path), kwargs={'append':True, 'truncate_stop':True}).value
        assert fasta_sequences(path) == ['AB*A*B', 'B', 'AB']
        invoke(write, x[:1], alphabet, str(path), kwargs={'truncate_stop':True}).value
        assert fasta_sequences(path) == ['AB']


def test_f20_t09():
    with isolated_state(seed=209, dtype=torch.float64):
        residue = torch.tensor([[.81,.19],[.26,.74]])
        insertion = torch.tensor([[.33,.67],[.62,.38],[.17,.83]])
        r = torch.tensor([[[.77,.23],[.59,.41],[.68,.32]],[[.54,.46],[.72,.28],[.39,.61]]])
        u = torch.tensor([[[.61,.39],[.83,.17],[.46,.54]],[[.78,.22],[.64,.36],[.57,.43]]])
        params = invoke(Profile(2), *(v.log() for v in (residue,insertion,r,u))).value
        law = MissingDataDiscreteHMM(*params)
        # Score every short word, including terminal insertion and skipped precursors.
        import itertools
        for length in (1, 2, 4):
            for word in itertools.product(range(2), repeat=length):
                data = torch.eye(2)[list(word)]
                expected = alignment_probability(residue, insertion, r, u, data)
                assert_close(law.log_prob(data), np.log(expected))
        profile = ProfileHMM(2, 2)
        fixed = dict(zip(('precursor_seq','insert_seq','insert','delete'), (v.log() for v in (residue,insertion,r,u))))
        data = torch.eye(2)[[1,0,1,1]][None]
        trace = sequence_trace(profile, data, fixed)
        assert_close(trace.nodes['obs_seq']['fn'].log_prob(data), np.log(alignment_probability(residue,insertion,r,u,data[0])))


def test_f20_t10():
    for options in ({}, {'prior_scale':1.7, 'indel_prior_bias':2.3}):
        with isolated_state(seed=210, dtype=torch.float64):
            model = ProfileHMM(2, 3, **options)
            data = torch.eye(3)[[0,2]][None]
            trace = sequence_trace(model, data)
            for name in ('precursor_seq','insert_seq','insert','delete'):
                mean = np.array([options.get('indel_prior_bias',10.),0.]) if name in ('insert','delete') else 0.
                normal_site(trace.nodes[name], mean, options.get('prior_scale',1.))
            guide = sequence_trace(model, data, guide=True)
            for name in ('precursor_seq','insert_seq','insert','delete'):
                law = guide.nodes[name]['fn'].base_dist
                assert torch.all(law.scale > 0)
                normal_site(guide.nodes[name], law.loc.detach().numpy(), law.scale.detach().numpy())
            fixed = sequence_draws(trace)
            components = profile_components(model, fixed)
            assert_close(trace.nodes['obs_seq']['fn'].log_prob(data), np.log(alignment_probability(*components,data[0])))


def test_f20_t11():
    for family, ard, custom in [('Normal',False,False),('Laplace',True,True)]:
        with isolated_state(seed=211, dtype=torch.float64):
            options = {'weights_prior_scale':1.6,'offset_prior_scale':.7,'inverse_temp_prior':2.4} if custom else {}
            model = FactorMuE(3, 2, 2, latent_seq_length=2, z_prior_distribution=family, ARD_prior=ard, **options)
            data = torch.eye(2)[[0,1,0]][None]
            trace = sequence_trace(model, data)
            if ard:
                alpha = trace.nodes['alpha']['value'].numpy()
                site = trace.nodes['alpha']
                assert_close(site['fn'].log_prob(site['value']), stats.gamma.logpdf(alpha,1.,scale=1.).sum())
            else:
                alpha = np.ones(2)
                assert 'alpha' not in trace.nodes
            # Original adds a numerical epsilon; its effect is below this score precision.
            normal_site(trace.nodes['W'], 0., options.get('weights_prior_scale',1.)/alpha[:,None])
            normal_site(trace.nodes['B'], 0., options.get('offset_prior_scale',1.))
            normal_site(trace.nodes['inverse_temp'], options.get('inverse_temp_prior',100.), 1.)
            latent = trace.nodes['latent']
            reference = stats.norm if family == 'Normal' else stats.laplace
            assert_close(latent['fn'].log_prob(latent['value']), reference.logpdf(latent['value'].numpy()).sum(-1))
            # Caller-provided affine inputs exercise both coordinates, offsets and sharpness.
            width = trace.nodes['B']['value'].numel()
            W = torch.linspace(-.5,.8,2*width).reshape(2,width)
            B = torch.linspace(.7,-.3,width)
            z = torch.tensor([[-.8,.6],[.4,-1.2]])
            temp = torch.tensor(.9)
            decoded = model.decoder(z,W,B,temp)
            v = (z.numpy() @ W.numpy()+B.numpy())*np.logaddexp(0.,temp.numpy())
            for name, values in [('precursor_seq_logits',v[:,:4].reshape(2,2,2)),('insert_seq_logits',v[:,4:].reshape(2,3,2))]:
                expected = np.exp(values-values.max(-1,keepdims=True)); expected /= expected.sum(-1,keepdims=True)
                assert_close(decoded[name].exp(), expected)


def test_f20_t12():
    for dependent, substitution, custom in [(False,True,False),(True,True,True),(False,False,True)]:
        with isolated_state(seed=212, dtype=torch.float64):
            options = dict(indel_prior_scale=1.4,indel_prior_bias=1.8,substitution_prior_scale=.8,latent_seq_length=2,latent_alphabet_length=3) if custom else {}
            model = FactorMuE(10, 2, 2, indel_factor_dependence=dependent, substitution_matrix=substitution, inverse_temp_prior=1., **options)
            assert model.latent_seq_length == (2 if custom else 11)
            assert model.latent_alphabet_length == (3 if custom and substitution else 2)
            data = torch.eye(2)[[0,1,1]][None]
            trace = sequence_trace(model, data)
            if substitution:
                normal_site(trace.nodes['substitute'],0.,options.get('substitution_prior_scale',10.))
            else:
                assert 'substitute' not in trace.nodes
            if not dependent:
                for name in ('insert','delete'):
                    normal_site(trace.nodes[name],np.array([options.get('indel_prior_bias',10.),0.]),options.get('indel_prior_scale',1.))
            fixed = sequence_draws(trace)
            if dependent:
                decoded = model.decoder(fixed['latent'],fixed['W'],fixed['B'],fixed['inverse_temp'])
                v = fixed['latent'] @ fixed['W']+fixed['B']
                offset = (2*model.latent_seq_length+1)*model.latent_alphabet_length
                size = model.latent_seq_length*6
                for i,name in enumerate(('insert_logits','delete_logits')):
                    weights = v[:,offset+i*size:offset+(i+1)*size].reshape(1,model.latent_seq_length,3,2)+torch.tensor([1.8,0.])
                    assert_close(decoded[name].exp(),weights.softmax(-1))
            components = profile_components(model,fixed)
            assert_close(trace.nodes['obs_seq']['fn'].log_prob(data),np.log(alignment_probability(*components,data[0])))
