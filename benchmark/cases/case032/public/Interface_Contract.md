# Interface Contract

Import the Python package `velnora` and its public submodules using their dotted import paths. Numerical inputs and outputs are scalars or array-like values compatible with `jax` and `jax.numpy`; returned numerical arrays support shape inspection, numerical conversion with `numpy.asarray`, and compiled, vectorized, and differentiated calls through `jax.jit`, `jax.vmap`, and `jax.grad`.

Signatures below use `...` to mark an optional argument, without specifying its default value. A `rng_key` or `key` accepts a JAX random key. Calibration also accepts the legacy `jax.random.PRNGKey` array. Model callables receive caller-supplied positional and named arguments; result dictionaries use caller-supplied site names as string keys.

## `velnora.distributions.Normal`

`Normal(loc=..., scale=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`batch_shape` and `event_shape` are tuples of integers identifying batch and event dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

`cdf(value)` returns a numerical array of cumulative probabilities. `icdf(q)` accepts a numerical probability array and returns the corresponding numerical quantile array.

`expand(batch_shape)` and `to_event(reinterpreted_batch_ndims)` return distribution objects. `mask(mask)` accepts a boolean or boolean array and returns a distribution object.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Incompatible distribution shape requests raise `ValueError`.

## `velnora.distributions.Cauchy`

`Cauchy(loc=..., scale=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

`cdf(value)` returns a numerical array of cumulative probabilities. `icdf(q)` accepts a numerical probability array and returns the corresponding numerical quantile array.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

## `velnora.distributions.HalfNormal`

`HalfNormal(scale=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.HalfCauchy`

`HalfCauchy(scale=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`cdf(value)` returns a numerical array of cumulative probabilities. `icdf(q)` accepts a numerical probability array and returns the corresponding numerical quantile array.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.StudentT`

`StudentT(df, loc=..., scale=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

`to_event(reinterpreted_batch_ndims)` return distribution objects.

## `velnora.distributions.Laplace`

`Laplace(loc=..., scale=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

`cdf(value)` returns a numerical array of cumulative probabilities. `icdf(q)` accepts a numerical probability array and returns the corresponding numerical quantile array.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

## `velnora.distributions.AsymmetricLaplace`

`AsymmetricLaplace(loc=..., scale=..., asymmetry=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

## `velnora.distributions.AsymmetricLaplaceQuantile`

`AsymmetricLaplaceQuantile(loc=..., scale=..., quantile=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

## `velnora.distributions.SoftLaplace`

`SoftLaplace(loc, scale, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

## `velnora.distributions.Logistic`

`Logistic(loc=..., scale=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

`cdf(value)` returns a numerical array of cumulative probabilities. `icdf(q)` accepts a numerical probability array and returns the corresponding numerical quantile array.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

## `velnora.distributions.Uniform`

`Uniform(low=..., high=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

`cdf(value)` returns a numerical array of cumulative probabilities. `icdf(q)` accepts a numerical probability array and returns the corresponding numerical quantile array.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.LogUniform`

`LogUniform(low, high, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.LogNormal`

`LogNormal(loc=..., scale=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

`expand(batch_shape)` and `to_event(reinterpreted_batch_ndims)` return distribution objects.

## `velnora.distributions.Exponential`

`Exponential(rate=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

`cdf(value)` returns a numerical array of cumulative probabilities. `icdf(q)` accepts a numerical probability array and returns the corresponding numerical quantile array.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Gamma`

`Gamma(concentration, rate=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.InverseGamma`

`InverseGamma(concentration, rate=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Chi2`

`Chi2(df, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Beta`

`Beta(concentration1, concentration0, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

`cdf(value)` returns a numerical array of cumulative probabilities. `icdf(q)` accepts a numerical probability array and returns the corresponding numerical quantile array.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.BetaProportion`

`BetaProportion(mean, concentration, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Kumaraswamy`

`Kumaraswamy(concentration1, concentration0, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Pareto`

`Pareto(scale, alpha, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Weibull`

`Weibull(scale, concentration, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

`cdf(value)` returns a numerical array of cumulative probabilities.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Gumbel`

`Gumbel(loc=..., scale=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

## `velnora.distributions.Gompertz`

`Gompertz(concentration, rate=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Levy`

`Levy(loc, scale, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Dagum`

`Dagum(concentration, sharpness, scale, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Bernoulli`

`Bernoulli(probs=..., logits=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

`enumerate_support(expand=...)` returns an array with an enumeration axis followed by batch axes. `expand` is boolean; unexpanded batch axes have size one. Unsupported enumeration raises `NotImplementedError`.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Binomial`

`Binomial(total_count=..., probs=..., logits=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`enumerate_support(expand=...)` returns an array with an enumeration axis followed by batch axes. `expand` is boolean; unexpanded batch axes have size one. Unsupported enumeration raises `NotImplementedError`.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Categorical`

`Categorical(probs=..., logits=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

`enumerate_support(expand=...)` returns an array with an enumeration axis followed by batch axes. `expand` is boolean; unexpanded batch axes have size one. Unsupported enumeration raises `NotImplementedError`.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Multinomial`

`Multinomial(total_count=..., probs=..., logits=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Poisson`

`Poisson(rate, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Geometric`

`Geometric(probs=..., logits=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.DiscreteUniform`

`DiscreteUniform(low=..., high=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

`enumerate_support(expand=...)` returns an array with an enumeration axis followed by batch axes. `expand` is boolean; unexpanded batch axes have size one. Unsupported enumeration raises `NotImplementedError`.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.NegativeBinomial`

`NegativeBinomial(total_count, probs=..., logits=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.NegativeBinomial2`

`NegativeBinomial2(mean, concentration, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.BetaBinomial`

`BetaBinomial(concentration1, concentration0, total_count=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`enumerate_support(expand=...)` returns an array with an enumeration axis followed by batch axes. `expand` is boolean; unexpanded batch axes have size one. Unsupported enumeration raises `NotImplementedError`.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.BetaNegativeBinomial`

`BetaNegativeBinomial(concentration1, concentration0, n, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.DirichletMultinomial`

`DirichletMultinomial(concentration, total_count=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.GammaPoisson`

`GammaPoisson(concentration, rate=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.OrderedLogistic`

`OrderedLogistic(predictor, cutpoints, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`enumerate_support(expand=...)` returns an array with an enumeration axis followed by batch axes. `expand` is boolean; unexpanded batch axes have size one. Unsupported enumeration raises `NotImplementedError`.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.MultivariateNormal`

`MultivariateNormal(loc=..., covariance_matrix=..., precision_matrix=..., scale_tril=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`batch_shape` and `event_shape` are tuples of integers identifying batch and event dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

`expand(batch_shape)` and `to_event(reinterpreted_batch_ndims)` return distribution objects.

## `velnora.distributions.LowRankMultivariateNormal`

`LowRankMultivariateNormal(loc, cov_factor, cov_diag)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

## `velnora.distributions.MultivariateStudentT`

`MultivariateStudentT(df, loc=..., scale_tril=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

## `velnora.distributions.CAR`

`CAR(loc, correlation, conditional_precision, adj_matrix, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

## `velnora.distributions.Dirichlet`

`Dirichlet(concentration, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.MatrixNormal`

`MatrixNormal(loc, scale_tril_row, scale_tril_column)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.Wishart`

`Wishart(concentration, scale_matrix=..., rate_matrix=..., scale_tril=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.InverseWishart`

`InverseWishart(concentration, scale_matrix=..., rate_matrix=..., scale_tril=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.WishartCholesky`

`WishartCholesky(concentration, scale_matrix=..., rate_matrix=..., scale_tril=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.InverseWishartCholesky`

`InverseWishartCholesky(concentration, scale_matrix=..., rate_matrix=..., scale_tril=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.LKJ`

`LKJ(dimension, concentration=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.LKJCholesky`

`LKJCholesky(dimension, concentration=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.VonMises`

`VonMises(loc, concentration, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

`to_event(reinterpreted_batch_ndims)` return distribution objects.

## `velnora.distributions.SineBivariateVonMises`

`SineBivariateVonMises(phi_loc, psi_loc, phi_concentration, psi_concentration, correlation=..., weighted_correlation=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.SineSkewed`

`SineSkewed(base_dist, skewness)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.ProjectedNormal`

`ProjectedNormal(concentration)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Unsupported density evaluation raises `NotImplementedError`.

## `velnora.distributions.GaussianRandomWalk`

`GaussianRandomWalk(scale=..., num_steps=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

## `velnora.distributions.GaussianStateSpace`

`GaussianStateSpace(num_steps, transition_matrix, covariance_matrix=..., precision_matrix=..., scale_tril=..., initial_value=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

## `velnora.distributions.ZeroSumNormal`

`ZeroSumNormal(scale, event_shape, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.EulerMaruyama`

`EulerMaruyama(t, sde_fn, init_dist)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`sde_fn(value, time)` is a caller-supplied callable returning `(drift, diffusion)`, two numerical values broadcastable to the current state; `init_dist` is a distribution object and `t` is a numerical time-grid array.

## `velnora.distributions.CirculantNormal`

`CirculantNormal(loc, covariance_row=..., covariance_rfft=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`mean` and `variance` expose numerical population moment arrays, broadcastable to the batch and event dimensions.

`entropy()` returns a numerical array of entropy values with batch dimensions.

## `velnora.distributions.RelaxedBernoulli`

`RelaxedBernoulli(temperature, probs=..., logits=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

Sample-validation diagnostics are Python `UserWarning` warnings; `log_prob` retains its numerical array return form.

## `velnora.distributions.Delta`

`Delta(v=..., log_density=..., event_dim=...)`. `v` and `log_density` are numerical scalars or arrays; `event_dim` is an integer. Returns a distribution object.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.MixtureSameFamily`

`MixtureSameFamily(mixing_distribution, component_distribution)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`batch_shape` and `event_shape` are tuples of integers identifying batch and event dimensions.

`sample_with_intermediates(key, sample_shape)` returns `(samples, intermediates)`. `intermediates` is a list whose first element is an integer array of component indices, with sample and batch dimensions.

Rejected mixture requests raise `AssertionError`.

## `velnora.distributions.MixtureGeneral`

`MixtureGeneral(mixing_distribution, component_distributions)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`batch_shape` and `event_shape` are tuples of integers identifying batch and event dimensions.

`sample_with_intermediates(key, sample_shape)` returns `(samples, intermediates)`. `intermediates` is a list whose first element is an integer array of component indices, with sample and batch dimensions.

Rejected mixture requests raise `ValueError`.

## `velnora.distributions.TruncatedDistribution`

`TruncatedDistribution(base_dist, low=..., high=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.TruncatedGamma`

`TruncatedGamma(concentration=..., rate=..., *, low=..., high=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.DoublyTruncatedPowerLaw`

`DoublyTruncatedPowerLaw(alpha, low, high, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

## `velnora.distributions.LowerTruncatedPowerLaw`

`LowerTruncatedPowerLaw(alpha, low, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

## `velnora.distributions.LeftCensoredDistribution`

`LeftCensoredDistribution(base_dist, censored=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

`censored` are boolean scalars or arrays. Rejected base-law requests raise `TypeError`.

## `velnora.distributions.RightCensoredDistribution`

`RightCensoredDistribution(base_dist, censored=..., *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

`censored` are boolean scalars or arrays. Rejected base-law requests raise `TypeError`.

## `velnora.distributions.IntervalCensoredDistribution`

`IntervalCensoredDistribution(base_dist, left_censored, right_censored, *, validate_args=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

Rejected parameter requests with `validate_args=True` raise `ValueError`.

`left_censored` and `right_censored` are boolean scalars or arrays. `log_prob(value)` receives a final axis containing the lower and upper endpoints. Rejected base-law requests raise `TypeError`. Support-validation diagnostics use `UserWarning`.

## `velnora.distributions.ZeroInflatedDistribution`

`ZeroInflatedDistribution(base_dist, *, gate=..., gate_logits=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.ZeroInflatedPoisson`

`ZeroInflatedPoisson(gate, rate=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.ZeroInflatedNegativeBinomial2`

`ZeroInflatedNegativeBinomial2(mean, concentration, *, gate=..., gate_logits=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.HurdlePoisson`

`HurdlePoisson(gate, rate=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.HurdleNegativeBinomial2`

`HurdleNegativeBinomial2(gate, mean, concentration)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.HurdleGamma`

`HurdleGamma(gate, concentration, rate=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.HurdleLogNormal`

`HurdleLogNormal(gate, loc=..., scale=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.FoldedDistribution`

`FoldedDistribution(base_dist)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.GaussianCopula`

`GaussianCopula(marginal_dist, correlation_matrix=..., correlation_cholesky=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`batch_shape` and `event_shape` are tuples of integers identifying batch and event dimensions.

## `velnora.distributions.GaussianCopulaBeta`

`GaussianCopulaBeta(concentration1, concentration0, correlation_matrix=..., correlation_cholesky=...)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

## `velnora.distributions.ImproperUniform`

`ImproperUniform(support, batch_shape, event_shape)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`log_prob(value)` returns a numerical array with sample and batch dimensions. An unsupported `sample(key, sample_shape=...)` request raises `NotImplementedError`.

`batch_shape` and `event_shape` are tuples of integers identifying batch and event dimensions.

## `velnora.distributions.Unit`

`Unit(log_factor)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`batch_shape` and `event_shape` are tuples of integers identifying batch and event dimensions.

## `velnora.distributions.TransformedDistribution`

`TransformedDistribution(base_distribution, transforms)`. Returns a distribution object. Numerical parameters accept Python scalars and numerical arrays.

`sample(key, sample_shape=...)` returns a numerical sample array. `sample_shape` is a tuple of dimensions; sample dimensions precede batch dimensions and event dimensions. `log_prob(value)` returns a numerical array of log probabilities with sample and batch dimensions.

`batch_shape` and `event_shape` are tuples of integers identifying batch and event dimensions.

`to_event(reinterpreted_batch_ndims)` returns a distribution object.

## `velnora.distributions.kl_divergence`

`kl_divergence(p, q)` accepts two distribution objects and returns a numerical array with their broadcast batch shape. Unsupported operations raise `NotImplementedError`.

## `velnora.validation_enabled`

`validation_enabled()` returns a context manager for distribution validation.

## `velnora.distributions.constraints.boolean`

`boolean` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.real`

`real` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.extended_real`

`extended_real` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.positive`

`positive` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.nonnegative`

`nonnegative` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.interval`

`interval(lower_bound, upper_bound)` returns a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.open_interval`

`open_interval(lower_bound, upper_bound)` returns a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.greater_than`

`greater_than(lower_bound)` returns a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.greater_than_eq`

`greater_than_eq(lower_bound)` returns a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.less_than`

`less_than(upper_bound)` returns a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.integer_interval`

`integer_interval(lower_bound, upper_bound)` returns a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.integer_greater_than`

`integer_greater_than(lower_bound)` returns a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.positive_integer`

`positive_integer` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.nonnegative_integer`

`nonnegative_integer` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.circular`

`circular` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.real_vector`

`real_vector` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.real_matrix`

`real_matrix` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.complex`

`complex` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.simplex`

`simplex` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.softmax_logits`

`softmax_logits` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.multinomial`

`multinomial(upper_bound)` returns a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.ordered_vector`

`ordered_vector` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.positive_ordered_vector`

`positive_ordered_vector` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.sphere`

`sphere` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.l1_ball`

`l1_ball` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.lower_cholesky`

`lower_cholesky` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.scaled_unit_lower_cholesky`

`scaled_unit_lower_cholesky` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.corr_cholesky`

`corr_cholesky` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.corr_matrix`

`corr_matrix` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.positive_definite`

`positive_definite` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.positive_semidefinite`

`positive_semidefinite` is a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.zero_sum`

`zero_sum(event_dim=...)` returns a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

`event_dim` is an integer attribute giving the number of event axes.

## `velnora.distributions.constraints.cat`

`cat(cseq, dim=..., lengths=...)` returns a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.independent`

`independent(base_constraint, reinterpreted_batch_ndims)` returns a constraint object. Calling the object with a numerical `value` returns a boolean membership array, with event dimensions removed.

`feasible_like(prototype)` accepts a numerical array and returns a numerical array with the same shape.

## `velnora.distributions.constraints.dependent`

`dependent(value)` raises `ValueError` when membership is not defined.

## `velnora.distributions.constraints.unit_interval`

`unit_interval` is a constraint object accepted by the `constraint` option of `velnora.param`.

## `velnora.distributions.transforms.IdentityTransform`

`IdentityTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.AffineTransform`

`AffineTransform(loc, scale)` returns a transform object. `loc` and `scale` are numerical scalars or arrays.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.ExpTransform`

`ExpTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.SigmoidTransform`

`SigmoidTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.SoftplusTransform`

`SoftplusTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.PowerTransform`

`PowerTransform(exponent)` returns a transform object. `exponent` is numerical.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.AbsTransform`

`AbsTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

## `velnora.distributions.transforms.OrderedTransform`

`OrderedTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.StickBreakingTransform`

`StickBreakingTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.L1BallTransform`

`L1BallTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.LowerCholeskyTransform`

`LowerCholeskyTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.SoftplusLowerCholeskyTransform`

`SoftplusLowerCholeskyTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.ScaledUnitLowerCholeskyTransform`

`ScaledUnitLowerCholeskyTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.CorrCholeskyTransform`

`CorrCholeskyTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.PermuteTransform`

`PermuteTransform(permutation)` returns a transform object. `permutation` is a one-dimensional integer array.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.ReshapeTransform`

`ReshapeTransform(forward_shape, inverse_shape)` returns a transform object. `forward_shape` and `inverse_shape` are integer dimension tuples.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

Rejected reshape requests raise `ValueError`.

## `velnora.distributions.transforms.ComplexTransform`

`ComplexTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.ZeroSumTransform`

`ZeroSumTransform(transform_ndims=...)` returns a transform object. `transform_ndims` is an integer.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.DiscreteCosineTransform`

`DiscreteCosineTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.HaarTransform`

`HaarTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.RealFastFourierTransform`

`RealFastFourierTransform(transform_shape=..., transform_ndims=...)` returns a transform object. `transform_shape` is an integer dimension tuple and `transform_ndims` an integer.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.PackRealFastFourierCoefficientsTransform`

`PackRealFastFourierCoefficientsTransform(transform_shape=...)` returns a transform object. `transform_shape` is an integer dimension tuple.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.ComposeTransform`

`ComposeTransform(parts)` returns a transform object. `parts` is a sequence of transform objects.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

## `velnora.distributions.transforms.CatTransform`

`CatTransform(tseq, dim=..., lengths=...)` returns a transform object. `tseq` is a sequence of transform objects; `dim` is an integer and `lengths` a sequence of integers.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

## `velnora.distributions.transforms.IndependentTransform`

`IndependentTransform(base_transform, reinterpreted_batch_ndims)` returns a transform object. `base_transform` is a transform and `reinterpreted_batch_ndims` an integer.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

## `velnora.distributions.transforms.UnpackTransform`

`UnpackTransform(unpack_fn, pack_fn=...)` returns a transform object. `unpack_fn` and `pack_fn` are callables.

`__call__(x)` returns the container structure produced by the supplied `unpack_fn`. Leading batch dimensions are retained on the numerical leaves. `inv` is callable on that structure and returns a numerical array. `log_abs_det_jacobian(x, y)` returns an array with batch dimensions. An unsupported inverse raises `NotImplementedError`.

## `velnora.distributions.transforms.CholeskyTransform`

`CholeskyTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

## `velnora.distributions.transforms.CorrMatrixCholeskyTransform`

`CorrMatrixCholeskyTransform()` returns a transform object.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

## `velnora.distributions.transforms.LowerCholeskyAffine`

`LowerCholeskyAffine(loc, scale_tril)` returns a transform object. `loc` is a numerical vector and `scale_tril` a numerical matrix.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.transforms.SimplexToOrderedTransform`

`SimplexToOrderedTransform(anchor_point=...)` returns a transform object. `anchor_point` is numerical.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

## `velnora.distributions.transforms.RecursiveLinearTransform`

`RecursiveLinearTransform(transition_matrix, initial_value=...)` returns a transform object. `transition_matrix` is a numerical square matrix and `initial_value` a numerical vector.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

## `velnora.distributions.flows.InverseAutoregressiveTransform`

`InverseAutoregressiveTransform(autoregressive_nn, log_scale_min_clip=..., log_scale_max_clip=...)`. Transform constructors accept numerical parameters, integer shape tuples, integer permutations, transform objects, or callables in the argument positions indicated by their names.

`__call__(x)`, equivalently `transform(x)`, returns the transformed numerical value.

`inv` is an inverse transform object and is callable with the transformed value. `domain` and `codomain` are callable constraints. `log_abs_det_jacobian(x, y)` returns numerical log absolute Jacobian-volume values, with one value per batch event.

`forward_shape(shape)` and `inverse_shape(shape)` accept integer shape tuples and return integer shape tuples.

`autoregressive_nn(x)` returns `(mean, log_scale)`, numerical location and logarithmic multiplicative-scale arrays. `log_scale_min_clip` and `log_scale_max_clip` are numerical arguments.

## `velnora.distributions.flows.BlockNeuralAutoregressiveTransform`

`BlockNeuralAutoregressiveTransform(bn_arn)`. `bn_arn(x)` is a callable returning `(output, logs)`: transformed numerical coordinates and coordinate log-volume contributions.

`transform(x)` returns a numerical array. `inv` is a transform object accepted by `TransformedDistribution`. `log_abs_det_jacobian(x, y)` returns a scalar numerical log volume per event.

## `velnora.distributions.transforms.biject_to`

`biject_to(constraint)` returns a transform with callable forward and `inv` interfaces, callable `domain` and `codomain`, shape methods, and `log_abs_det_jacobian(x, y)`. Unsupported registrations raise `NotImplementedError`.

## `velnora.distributions.biject_to`

`biject_to(constraint)` returns a transform with callable forward and `inv` interfaces, callable `domain` and `codomain`, shape methods, and `log_abs_det_jacobian(x, y)`. Unsupported registrations raise `NotImplementedError`.

## `velnora.nn.AutoregressiveNN`

`AutoregressiveNN(input_dim, hidden_dims, param_dims=..., permutation=..., skip_connections=..., nonlinearity=...)` returns `(init_fn, apply_fn)`. `init_fn(rng_key, input_shape)` returns a pair whose second element is `params`, a tree of trainable numerical arrays. `apply_fn(params, inputs)` accepts those parameters and numerical input arrays.

For one parameter group, application returns one array; for multiple groups it returns a tuple of arrays in the supplied `param_dims` order. When all group multiplicities are one, each group has the input batch and coordinate shape. Otherwise each group has its multiplicity axis followed by input batch and coordinate axes.

`input_dim` is an integer; `hidden_dims` and `param_dims` are sequences of integers; `permutation` is a one-dimensional integer array; `skip_connections` is boolean; `nonlinearity` is an initialization-and-application pair.

## `velnora.nn.BlockNeuralAutoregressiveNN`

`BlockNeuralAutoregressiveNN(input_dim, hidden_factors=..., residual=...)` returns `(init_fn, apply_fn)`. `init_fn(rng_key, input_shape)` returns a pair whose second element is `params`, a tree of trainable numerical arrays. `apply_fn(params, inputs)` accepts those parameters and numerical input arrays.

Application returns `(output, logs)`, two numerical arrays with the input batch and coordinate shape; `logs` carries the coordinate contributions to the log absolute Jacobian determinant.

`input_dim` is an integer, `hidden_factors` a sequence of integers, and `residual` a string or `None`.

The `residual` forms are `None` for no residual connection, `"normal"` for a normal residual connection, and `"gated"` for a gated residual connection.

## `velnora.sample`

`sample(name, fn, *, obs=..., rng_key=..., sample_shape=..., infer=..., obs_mask=...)`.

Returns a numerical site value. `name` is a string, `fn` a distribution, `obs` an optional numerical observation, `rng_key` a random key, `sample_shape` a dimension tuple, and `obs_mask` a boolean scalar or array. `infer` is a mapping carrying caller metadata and configuration keys `enumerate` and `branching`.

The `infer` entry `enumerate` uses `"parallel"` to select parallel enumeration.

## `velnora.param`

`param(name, init_value=..., **kwargs)`.

Returns the bound numerical parameter. `init_value` is a numerical value or a callable receiving a random key. Named options `constraint` and `event_dim` accept a constraint object and an integer, respectively.

## `velnora.deterministic`

`deterministic(name, value)`.

Returns the supplied value and exposes it under the string site name in execution records.

## `velnora.factor`

`factor(name, log_factor)`.

Accepts a string site name and a scalar or array-valued log contribution.

## `velnora.plate`

`plate(name, size, subsample_size=..., dim=...)`.

A context manager whose context value is an integer index array. `name` is a string; `size`, `subsample_size` and `dim` are integers. Rejected dimension requests raise `ValueError`; colliding dimensions raise `AssertionError`.

Under `velnora.handlers.substitute`, a `data` entry keyed by the plate's `name` supplies the subsample index array that the plate uses in place of a random selection.

## `velnora.plate_stack`

`plate_stack(prefix, sizes)`.

Returns a context manager. `prefix` is a string and `sizes` a sequence of integer dimensions.

## `velnora.subsample`

`subsample(data, event_dim)`.

Returns a numerical array of selected data. `event_dim` is an integer.

## `velnora.prng_key`

`prng_key()`.

Returns a random key usable by `jax.random`.

## `velnora.module`

`module(name, nn, input_shape=...)`.

Returns a callable network. `nn` is `(init_fn, apply_fn)`; `init_fn(rng_key, input_shape)` returns `(output_shape, params)` and `apply_fn(params, inputs)` returns network output. The supplied `input_shape` is an integer tuple. Existing parameter values are exchangeable through the string naming rule `<name>$params`. A rejected initialization request raises `ValueError`.

## `velnora.primitives.mutable`

`mutable(name, init_value)` accepts a string name and an initial dictionary, and returns a mutable dictionary. The dictionary can contain numerical arrays and caller-defined keys.

## `velnora.handlers.trace`

`trace(fn=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

`get_trace(*args, **kwargs)` returns an execution mapping keyed by string site names. The context manager yields the same mapping form. Each reached record exposes `value`, `type`, and `name`; random-site records additionally expose `fn` (the distribution), `is_observed` (boolean), `infer` (metadata mapping), and `cond_indep_stack` (a sequence of frames). Each frame exposes `name`, `dim`, and `size`.

The site-kind strings read through `type` are `sample`, `param`, and `deterministic`. Duplicate-site failures raise `AssertionError`.

## `velnora.handlers.seed`

`seed(fn=..., rng_seed=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

`rng_seed` accepts an integer seed or a random key.

## `velnora.handlers.substitute`

`substitute(fn=..., data=..., substitute_fn=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

`data` is a string-to-value mapping. The callback `substitute_fn(site)` receives a site record with `name` and returns a replacement value or `None`.

## `velnora.handlers.replay`

`replay(fn=..., trace=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

`trace` accepts an execution mapping. Rejected replay requests raise `RuntimeError`.

## `velnora.handlers.condition`

`condition(fn=..., data=..., condition_fn=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

`data` is a string-to-value mapping. The callback `condition_fn(site)` receives a site record with `name` and returns a replacement value or `None`.

## `velnora.handlers.uncondition`

`uncondition(fn=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

## `velnora.handlers.block`

`block(fn=..., hide_fn=..., hide=..., expose_types=..., expose=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

`hide_fn(site)` is a predicate receiving `name`; `hide` and `expose` are sequences of site-name strings and `expose_types` is a sequence of site-kind strings.

## `velnora.handlers.scope`

`scope(fn=..., prefix=..., divider=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

`prefix` and `divider` are strings. Exposed names have the form `<prefix><divider><name>`.

## `velnora.handlers.scale`

`scale(fn=..., scale=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

`scale` accepts a numerical scalar or array. Rejected scale requests raise `ValueError`.

## `velnora.handlers.mask`

`mask(fn=..., mask=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

`mask` accepts a boolean scalar or boolean array.

## `velnora.handlers.lift`

`lift(fn=..., prior=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

`prior` accepts a distribution or a mapping from parameter names to distributions.

## `velnora.handlers.infer_config`

`infer_config(fn=..., config_fn=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

`config_fn(site)` accepts a site record with `name` and returns a mapping exposed in the record’s `infer` field.

## `velnora.handlers.do`

`do(fn=..., data=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

`data` is a mapping from site-name strings to intervention values.

## `velnora.handlers.collapse`

`collapse(fn=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

## `velnora.handlers.reparam`

`reparam(fn=..., config=...)`. A handler wraps a callable with the same call arguments and return structure, or is used as a context manager.

`config` is a mapping from string site names to reparameterization objects.

## `velnora.contrib.control_flow.scan`

`scan(f, init, xs, reverse=...)` accepts a callable `f(carry, item)` returning `(carry, output)`, an initial carry, and arrays or nested arrays with a sequence axis. It returns `(final_carry, outputs)`; output leaves and execution-record values carry a leading sequence axis. `reverse` is boolean.

## `velnora.contrib.control_flow.cond`

`cond(pred, true_fun, false_fun, operand)` accepts a boolean predicate and branch callables that accept the operand; its return has the selected branch’s return structure. Unsupported enumeration raises `RuntimeError`.

## `velnora.infer.util.compute_log_probs`

`compute_log_probs(model, model_args, model_kwargs, params, sum_log_prob=...)`. `model` is callable, `model_args` is a tuple, `model_kwargs` is a mapping, and `params` is a site-name-to-value mapping.

Returns `(log_probs, trace)`. `log_probs` maps string site names to numerical scalars, or to arrays retaining independent batch dimensions when `sum_log_prob=False`. `trace` is an execution-record mapping.

## `velnora.infer.util.log_density`

`log_density(model, model_args, model_kwargs, params)`. `model` is callable, `model_args` is a tuple, `model_kwargs` is a mapping, and `params` is a site-name-to-value mapping.

Returns `(log_joint, trace)`: a numerical scalar log probability and an execution-record mapping.

## `velnora.infer.util.constrain_fn`

`constrain_fn(model, model_args, model_kwargs, params, return_deterministic=...)`. `model` is callable, `model_args` is a tuple, `model_kwargs` is a mapping, and `params` is a site-name-to-value mapping.

Returns a mapping from string site names to numerical values in the requested coordinates. `return_deterministic` is boolean.

## `velnora.infer.util.unconstrain_fn`

`unconstrain_fn(model, model_args, model_kwargs, params)`. `model` is callable, `model_args` is a tuple, `model_kwargs` is a mapping, and `params` is a site-name-to-value mapping.

Returns a mapping from string site names to numerical values in the requested coordinates.

## `velnora.infer.util.potential_energy`

`potential_energy(model, model_args, model_kwargs, params)`. `model` is callable, `model_args` is a tuple, `model_kwargs` is a mapping, and `params` is a site-name-to-value mapping.

Returns a scalar numerical potential energy.

## `velnora.infer.util.initialize_model`

`initialize_model(rng_key, model, *, init_strategy=...)` accepts a model callable and an initialization callable. Returns an object with `param_info`, `potential_fn`, and `postprocess_fn`.

`param_info.z` and `param_info.z_grad` are mappings of numerical latent coordinates and their potential derivatives. `param_info.potential_energy` is a numerical scalar. `potential_fn(z)` returns a numerical scalar; `postprocess_fn(z)` returns a site-name-to-value mapping. Failed model initialization raises `RuntimeError`.

## `velnora.infer.util.find_valid_initial_params`

`find_valid_initial_params(rng_key, model, *, init_strategy=...)` returns `((z, potential_energy, z_grad), is_valid)`. Coordinate and derivative values are site-name mappings, potential energy is a numerical scalar, and `is_valid` is a scalar boolean indicating whether a valid initial point was obtained.

## `velnora.infer.init_to_feasible`

`init_to_feasible(site=...)`. This initialization callable is accepted as `init_strategy` or `init_loc_fn`. Called without a site, it returns a site-initialization callable. Called with a site record, it returns a numerical initial value.

## `velnora.infer.initialization.init_to_feasible`

`init_to_feasible(site=...)`. This initialization callable is accepted as `init_strategy` or `init_loc_fn`. Called without a site, it returns a site-initialization callable. Called with a site record, it returns a numerical initial value.

## `velnora.infer.initialization.init_to_mean`

`init_to_mean(site=...)`. This initialization callable is accepted as `init_strategy` or `init_loc_fn`. Called without a site, it returns a site-initialization callable. Called with a site record, it returns a numerical initial value.

## `velnora.infer.initialization.init_to_sample`

`init_to_sample(site=...)`. This initialization callable is accepted as `init_strategy` or `init_loc_fn`. Called without a site, it returns a site-initialization callable. Called with a site record, it returns a numerical initial value.

## `velnora.infer.initialization.init_to_median`

`init_to_median(site=..., num_samples=...)`. This initialization callable is accepted as `init_strategy` or `init_loc_fn`. Called without a site, it returns a site-initialization callable. Called with a site record, it returns a numerical initial value.

`num_samples` is an integer.

## `velnora.infer.init_to_uniform`

`init_to_uniform(site=..., radius=...)`. This initialization callable is accepted as `init_strategy` or `init_loc_fn`. Called without a site, it returns a site-initialization callable. Called with a site record, it returns a numerical initial value.

`radius` is a numerical scalar.

## `velnora.infer.initialization.init_to_uniform`

`init_to_uniform(site=..., radius=...)`. This initialization callable is accepted as `init_strategy` or `init_loc_fn`. Called without a site, it returns a site-initialization callable. Called with a site record, it returns a numerical initial value.

`radius` is a numerical scalar.

## `velnora.infer.init_to_value`

`init_to_value(site=..., values=...)`. This initialization callable is accepted as `init_strategy` or `init_loc_fn`. Called without a site, it returns a site-initialization callable. Called with a site record, it returns a numerical initial value.

`values` is a mapping from string site names to numerical values.

## `velnora.infer.initialization.init_to_value`

Stated under `velnora.infer.init_to_value`.

## `velnora.contrib.funsor.config_enumerate`

`config_enumerate(fn)` accepts a model callable and returns a callable with its argument and return structures.

## `velnora.contrib.funsor.enum`

`enum(fn, first_available_dim=...)` accepts a model callable and an integer dimension; returns a model wrapper.

## `velnora.contrib.funsor.infer_discrete`

`infer_discrete(fn, *, temperature=..., rng_key=...)` returns a callable accepting the model’s original arguments and returning its original result structure with numerical discrete values. `temperature` is numerical and `rng_key` is a random key. Rejected requests raise `ValueError`.

## `velnora.contrib.funsor.infer_util.log_density`

`log_density(model, model_args, model_kwargs, params)` returns `(log_joint, trace)`: a numerical scalar and an execution-record mapping. Arguments are a model callable, a positional tuple, a keyword mapping, and a string-to-value mapping.

## `velnora.ops.indexing.Vindex`

`Vindex(tensor)[indices]` accepts a numerical array and an indexing tuple containing integer scalars or arrays, full slices, and a leading ellipsis. It returns a numerical array with broadcast index-batch axes and retained event axes.

## `velnora.infer.Trace_ELBO`

`Trace_ELBO(num_particles=..., vectorize_particles=..., multi_sample_guide=...)` returns an objective object. `num_particles` is an integer. `vectorize_particles` is boolean. `multi_sample_guide` is boolean.

`loss(rng_key, param_map, model, guide, *args, **kwargs)` returns a scalar numerical objective. `param_map` is a parameter mapping and `model` and `guide` are callables.

## `velnora.infer.TraceMeanField_ELBO`

`TraceMeanField_ELBO(num_particles=..., vectorize_particles=...)` returns an objective object. `num_particles` is an integer. `vectorize_particles` is boolean.

`loss(rng_key, param_map, model, guide, *args, **kwargs)` returns a scalar numerical objective. `param_map` is a parameter mapping and `model` and `guide` are callables.

## `velnora.infer.TraceGraph_ELBO`

`TraceGraph_ELBO(num_particles=..., vectorize_particles=...)` returns an objective object. `num_particles` is an integer. `vectorize_particles` is boolean.

`loss(rng_key, param_map, model, guide, *args, **kwargs)` returns a scalar numerical objective. `param_map` is a parameter mapping and `model` and `guide` are callables.

## `velnora.infer.TraceEnum_ELBO`

`TraceEnum_ELBO(num_particles=..., vectorize_particles=...)` returns an objective object. `num_particles` is an integer. `vectorize_particles` is boolean.

`loss(rng_key, param_map, model, guide, *args, **kwargs)` returns a scalar numerical objective. `param_map` is a parameter mapping and `model` and `guide` are callables.

## `velnora.infer.RenyiELBO`

`RenyiELBO(alpha=..., num_particles=...)` returns an objective object. `num_particles` is an integer. `alpha` is numerical.

`loss(rng_key, param_map, model, guide, *args, **kwargs)` returns a scalar numerical objective. `param_map` is a parameter mapping and `model` and `guide` are callables.

Rejected objective specifications raise `ValueError`.

## `velnora.infer.SVI`

`SVI(model, guide, optim, loss)` accepts callable model and guide, an optimizer object or compatible Optax optimizer, and an objective object.

`init(rng_key, *args, init_params=..., **kwargs)` returns a reusable training state. `init_params` is a parameter mapping. `get_params(state)` returns a mapping from string parameter names to constrained numerical parameters. `state.mutable_state` is a mapping of named mutable dictionaries.

`evaluate(state, *args, **kwargs)` returns a numerical scalar objective. `update(state, *args, **kwargs)` and `stable_update(state, *args, **kwargs)` return `(next_state, loss)`, with a scalar numerical `loss`.

`run(rng_key, num_steps, *args, init_state=..., progress_bar=..., **kwargs)` returns an object with `params` (a constrained parameter mapping), `state` (a reusable training state), and `losses` (a numerical array of length `num_steps`). `progress_bar` is boolean. Rejected training requests raise `ValueError`.

## `velnora.optim.Adam`

`Adam(step_size, b1=..., b2=...)` returns an optimizer object. `step_size` accepts a numerical scalar or a callable from an integer update index to a numerical scalar.

`init(params)` returns reusable optimizer state; `update(g, state)` returns updated state; `get_params(state)` returns the numerical parameter tree, retaining the caller’s container and array shapes.

## `velnora.optim.Adagrad`

`Adagrad(step_size, momentum=...)` returns an optimizer object. `step_size` accepts a numerical scalar or a callable from an integer update index to a numerical scalar.

`init(params)` returns reusable optimizer state; `update(g, state)` returns updated state; `get_params(state)` returns the numerical parameter tree, retaining the caller’s container and array shapes.

## `velnora.optim.Momentum`

`Momentum(step_size, mass=...)` returns an optimizer object. `step_size` accepts a numerical scalar or a callable from an integer update index to a numerical scalar.

`init(params)` returns reusable optimizer state; `update(g, state)` returns updated state; `get_params(state)` returns the numerical parameter tree, retaining the caller’s container and array shapes.

## `velnora.optim.RMSProp`

`RMSProp(step_size, gamma=...)` returns an optimizer object. `step_size` accepts a numerical scalar or a callable from an integer update index to a numerical scalar.

`init(params)` returns reusable optimizer state; `update(g, state)` returns updated state; `get_params(state)` returns the numerical parameter tree, retaining the caller’s container and array shapes.

## `velnora.optim.RMSPropMomentum`

`RMSPropMomentum(step_size, gamma=..., momentum=...)` returns an optimizer object. `step_size` accepts a numerical scalar or a callable from an integer update index to a numerical scalar.

`init(params)` returns reusable optimizer state; `update(g, state)` returns updated state; `get_params(state)` returns the numerical parameter tree, retaining the caller’s container and array shapes.

## `velnora.optim.SGD`

`SGD(step_size)` returns an optimizer object. `step_size` accepts a numerical scalar or a callable from an integer update index to a numerical scalar.

`init(params)` returns reusable optimizer state; `update(g, state)` returns updated state; `get_params(state)` returns the numerical parameter tree, retaining the caller’s container and array shapes.

## `velnora.optim.SM3`

`SM3(step_size, momentum=...)` returns an optimizer object. `step_size` accepts a numerical scalar or a callable from an integer update index to a numerical scalar.

`init(params)` returns reusable optimizer state; `update(g, state)` returns updated state; `get_params(state)` returns the numerical parameter tree, retaining the caller’s container and array shapes.

## `velnora.optim.ClippedAdam`

`ClippedAdam(step_size, *, clip_norm=...)` returns an optimizer object. `step_size` accepts a numerical scalar or a callable from an integer update index to a numerical scalar.

`init(params)` returns reusable optimizer state; `update(g, state)` returns updated state; `get_params(state)` returns the numerical parameter tree, retaining the caller’s container and array shapes.

## `velnora.optim.Minimize`

`Minimize()` returns an optimizer object. The object is accepted by `SVI`.

## `velnora.optim.optax_to_velnora`

`optax_to_velnora(transformation)` accepts an Optax gradient transformation and returns an optimizer accepted by `SVI`.

## `velnora.infer.autoguide.AutoNormal`

`AutoNormal(model, *, prefix=..., init_loc_fn=..., init_scale=...)` returns a callable guide. `model` is callable. `prefix` is a string. `init_loc_fn` is an initialization callable. `init_scale` is numerical.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

`median(params)` returns a site-name-to-array mapping with each site’s batch and event shape.

`quantiles(params, quantiles)` accepts a one-dimensional probability sequence and returns a mapping of numerical arrays with a leading quantile axis followed by site dimensions.

Parameter names use `<site>_<prefix>_loc` and `<site>_<prefix>_scale`. Their arrays have each site’s batch and event shape, with a leading particle axis when used in particle inference. The readable `scale_constraint` attribute is a constraint object accepted by `biject_to`.

Rejected guide requests raise `ValueError`.

The parameter-name prefix is `auto` when `prefix` is omitted.

The `loc` and `scale` name suffixes identify unconstrained site locations and positive standard deviations, respectively.

## `velnora.infer.autoguide.AutoDiagonalNormal`

`AutoDiagonalNormal(model, *, init_scale=...)` returns a callable guide. `model` is callable. `init_scale` is numerical.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

`median(params)` returns a site-name-to-array mapping with each site’s batch and event shape.

`quantiles(params, quantiles)` accepts a one-dimensional probability sequence and returns a mapping of numerical arrays with a leading quantile axis followed by site dimensions.

Joint-coordinate parameter names use `<prefix>_loc` and `<prefix>_scale`. Arrays have a latent-coordinate axis and, for covariance factors, a trailing factor axis. Batched guides retain model batch axes before these axes.

`get_posterior(params)` returns a latent-coordinate distribution exposing numerical `mean` and `variance` arrays.

Rejected guide requests raise `ValueError`. Missing usable latent structure raises `RuntimeError`.

The parameter-name prefix is `auto` when `prefix` is omitted.

The `loc` and `scale` suffixes identify unconstrained locations and positive coordinate standard deviations.

## `velnora.infer.autoguide.AutoMultivariateNormal`

`AutoMultivariateNormal(model, *, init_scale=...)` returns a callable guide. `model` is callable. `init_scale` is numerical.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

`median(params)` returns a site-name-to-array mapping with each site’s batch and event shape.

`quantiles(params, quantiles)` accepts a one-dimensional probability sequence and returns a mapping of numerical arrays with a leading quantile axis followed by site dimensions.

Joint-coordinate parameter names use `<prefix>_loc` and `<prefix>_scale_tril`. Arrays have a latent-coordinate axis and, for covariance factors, a trailing factor axis. Batched guides retain model batch axes before these axes.

`get_transform(params)` returns a callable transform accepting a numerical latent-coordinate vector and returning a numerical vector.

Rejected guide requests raise `ValueError`. Missing usable latent structure raises `RuntimeError`.

The parameter-name prefix is `auto` when `prefix` is omitted.

The `loc` and `scale_tril` suffixes identify unconstrained locations and a covariance Cholesky factor.

## `velnora.infer.autoguide.AutoLowRankMultivariateNormal`

`AutoLowRankMultivariateNormal(model, *, init_scale=...)` returns a callable guide. `model` is callable. `init_scale` is numerical.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

`median(params)` returns a site-name-to-array mapping with each site’s batch and event shape.

`quantiles(params, quantiles)` accepts a one-dimensional probability sequence and returns a mapping of numerical arrays with a leading quantile axis followed by site dimensions.

Joint-coordinate parameter names use `<prefix>_loc` and `<prefix>_scale` and `<prefix>_cov_factor`. Arrays have a latent-coordinate axis and, for covariance factors, a trailing factor axis. Batched guides retain model batch axes before these axes.

Rejected guide requests raise `ValueError`. Missing usable latent structure raises `RuntimeError`.

The parameter-name prefix is `auto` when `prefix` is omitted.

The `loc`, `scale`, and `cov_factor` suffixes identify unconstrained locations, coordinate standard deviations, and covariance factors.

## `velnora.infer.autoguide.AutoBatchedMultivariateNormal`

`AutoBatchedMultivariateNormal(model, *, init_scale=...)` returns a callable guide. `model` is callable. `init_scale` is numerical.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

`median(params)` returns a site-name-to-array mapping with each site’s batch and event shape.

Joint-coordinate parameter names use `<prefix>_loc` and `<prefix>_scale_tril`. Arrays have a latent-coordinate axis and, for covariance factors, a trailing factor axis. Batched guides retain model batch axes before these axes.

Rejected guide requests raise `ValueError`. Missing usable latent structure raises `RuntimeError`.

The parameter-name prefix is `auto` when `prefix` is omitted.

The `loc` and `scale_tril` suffixes identify unconstrained locations and a covariance Cholesky factor.

## `velnora.infer.autoguide.AutoBatchedLowRankMultivariateNormal`

`AutoBatchedLowRankMultivariateNormal(model, *, init_scale=...)` returns a callable guide. `model` is callable. `init_scale` is numerical.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

`median(params)` returns a site-name-to-array mapping with each site’s batch and event shape.

Joint-coordinate parameter names use `<prefix>_loc` and `<prefix>_scale` and `<prefix>_cov_factor`. Arrays have a latent-coordinate axis and, for covariance factors, a trailing factor axis. Batched guides retain model batch axes before these axes.

Rejected guide requests raise `ValueError`. Missing usable latent structure raises `RuntimeError`.

The parameter-name prefix is `auto` when `prefix` is omitted.

The `loc`, `scale`, and `cov_factor` suffixes identify unconstrained locations, coordinate standard deviations, and covariance factors.

## `velnora.infer.autoguide.AutoDelta`

`AutoDelta(model, *, prefix=...)` returns a callable guide. `model` is callable. `prefix` is a string.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

`median(params)` returns a site-name-to-array mapping with each site’s batch and event shape.

Point parameter names use `<site>_<prefix>_loc`, with the model site’s shape.

Rejected guide requests raise `ValueError`.

The parameter-name prefix is `auto` when `prefix` is omitted.

The `loc` name suffix identifies original-domain point values.

## `velnora.infer.autoguide.AutoLaplaceApproximation`

`AutoLaplaceApproximation(model)` returns a callable guide. `model` is callable.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

`median(params)` returns a site-name-to-array mapping with each site’s batch and event shape.

`quantiles(params, quantiles)` accepts a one-dimensional probability sequence and returns a mapping of numerical arrays with a leading quantile axis followed by site dimensions.

The fitted location parameter name is `<prefix>_loc`.

Rejected guide requests raise `ValueError`. Missing usable latent structure raises `RuntimeError`.

The parameter-name prefix is `auto` when `prefix` is omitted.

The `loc` suffix identifies unconstrained locations.

## `velnora.infer.autoguide.AutoIAFNormal`

`AutoIAFNormal(model, *, num_flows=...)` returns a callable guide. `model` is callable. `num_flows` is an integer.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

Rejected guide requests raise `ValueError`. Missing usable latent structure raises `RuntimeError`.

## `velnora.infer.autoguide.AutoBNAFNormal`

`AutoBNAFNormal(model)` returns a callable guide. `model` is callable.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

Rejected guide requests raise `ValueError`. Missing usable latent structure raises `RuntimeError`.

## `velnora.infer.autoguide.AutoDAIS`

`AutoDAIS(model, *, K=...)` returns a callable guide. `model` is callable. `K` is an integer.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

Rejected guide requests raise `ValueError`. Missing usable latent structure raises `RuntimeError`.

## `velnora.infer.autoguide.AutoSurrogateLikelihoodDAIS`

`AutoSurrogateLikelihoodDAIS(model, surrogate_model, *, K=...)` returns a callable guide. `model` is callable. `surrogate_model` is callable. `K` is an integer.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

Rejected guide requests raise `ValueError`. Missing usable latent structure raises `RuntimeError`.

## `velnora.infer.autoguide.AutoSemiDAIS`

`AutoSemiDAIS(model, local_model, global_guide=..., *, K=...)` returns a callable guide. `model` is callable. `local_model` is callable and `global_guide` is a guide callable or `None`. `K` is an integer.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

Rejected guide requests raise `ValueError`.

## `velnora.infer.autoguide.AutoGuideList`

`AutoGuideList(model)` returns a callable guide. `model` is callable.

`guide(*args, **kwargs)` accepts model inputs and exposes parameter and sample sites in execution records. `sample_posterior(rng_key, params, *args, sample_shape=..., **kwargs)` returns a mapping from model site names to numerical arrays with leading `sample_shape` axes and the sites’ batch and event axes. `params` is a fitted parameter mapping.

`append(part)` accepts a guide object. The composed guide uses the parameter names exposed by its parts. Rejected composition requests raise `ValueError`.

## `velnora.infer.reparam.LocScaleReparam`

`LocScaleReparam(centered=..., shape_params=...)` returns an object accepted in the `config` mapping of `handlers.reparam`.

Exchanged auxiliary-site or parameter names use `<site>_decentered`, `<site>_centered`. Original model values are readable under the original site names in execution records.

`centered` is a numerical scalar or array, or `None`; `shape_params` is a sequence of parameter-name strings. Rejected reparameterization requests raise `ValueError`.

## `velnora.infer.reparam.TransformReparam`

`TransformReparam()` returns an object accepted in the `config` mapping of `handlers.reparam`.

Exchanged auxiliary-site or parameter names use `<site>_base`. Original model values are readable under the original site names in execution records.

Rejected observation reparameterization raises `AssertionError`.

## `velnora.infer.reparam.ProjectedNormalReparam`

`ProjectedNormalReparam()` returns an object accepted in the `config` mapping of `handlers.reparam`.

Exchanged auxiliary-site or parameter names use `<site>_normal`. Original model values are readable under the original site names in execution records.

Rejected observation reparameterization raises `AssertionError`.

## `velnora.infer.reparam.CircularReparam`

`CircularReparam()` returns an object accepted in the `config` mapping of `handlers.reparam`.

Exchanged auxiliary-site or parameter names use `<site>_unwrapped`. Original model values are readable under the original site names in execution records.

Rejected observation reparameterization raises `AssertionError`.

## `velnora.infer.reparam.ExplicitReparam`

`ExplicitReparam(transform)` returns an object accepted in the `config` mapping of `handlers.reparam`.

Exchanged auxiliary-site or parameter names use `<site>_base`. Original model values are readable under the original site names in execution records.

Rejected observation reparameterization raises `AssertionError`. Transform arguments are callable transform objects.

## `velnora.infer.reparam.UnitJacobianReparam`

`UnitJacobianReparam(transform)` returns an object accepted in the `config` mapping of `handlers.reparam`.

Exchanged auxiliary-site or parameter names use `<site>_transformed`. Original model values are readable under the original site names in execution records.

Rejected observation reparameterization raises `AssertionError`. Transform arguments are callable transform objects.

## `velnora.infer.reparam.HaarReparam`

`HaarReparam(dim=...)` returns an object accepted in the `config` mapping of `handlers.reparam`.

Exchanged auxiliary-site or parameter names use `<site>_haar`. Original model values are readable under the original site names in execution records.

Rejected observation reparameterization raises `AssertionError`.

## `velnora.infer.reparam.DiscreteCosineReparam`

`DiscreteCosineReparam(dim=...)` returns an object accepted in the `config` mapping of `handlers.reparam`.

Exchanged auxiliary-site or parameter names use `<site>_dct`. Original model values are readable under the original site names in execution records.

Rejected observation reparameterization raises `AssertionError`.

## `velnora.infer.reparam.NeuTraReparam`

`NeuTraReparam(guide, params)` returns an object accepted in the `config` mapping of `handlers.reparam`.

`reparam(fn)` returns a model wrapper. `transform_sample(latent)` returns a mapping of original site names to numerical sample arrays, retaining leading sample axes. Exchanged shared coordinates use the site-name form `<prefix>_shared_latent`. An incompatible guide interface raises `TypeError`; an incompatible transform raises `ValueError`.

## `velnora.infer.HMC`

`HMC(model=..., potential_fn=..., init_strategy=...)` returns a kernel accepted by `MCMC`. `model` is a model callable, `potential_fn` is a numerical scalar-valued callable on latent coordinates, and `init_strategy` is an initialization callable.

## `velnora.infer.MixedHMC`

`MixedHMC(inner_kernel)` returns a kernel accepted by `MCMC`. `inner_kernel` is a continuous kernel.

## `velnora.infer.NUTS`

`NUTS(model=..., potential_fn=..., init_strategy=...)` returns a kernel accepted by `MCMC`. `model` is a model callable, `potential_fn` is a numerical scalar-valued callable on latent coordinates, and `init_strategy` is an initialization callable.

## `velnora.infer.DiscreteGibbs`

`DiscreteGibbs(model)` returns a kernel accepted by `MCMC`. `model` is a model callable.

## `velnora.infer.DiscreteHMCGibbs`

`DiscreteHMCGibbs(inner_kernel)` returns a kernel accepted by `MCMC`. `inner_kernel` is a continuous kernel.

## `velnora.infer.ESS`

`ESS(model=..., potential_fn=..., moves=..., init_strategy=...)` returns a kernel accepted by `MCMC`. `model` is a model callable, `potential_fn` is a numerical scalar-valued callable on latent coordinates, and `init_strategy` is an initialization callable.

`RandomMove()` returns a move usable as a key in the `moves` mapping; mapping values are numerical weights. Rejected ensemble requests raise `AssertionError` or `ValueError`.

## `velnora.infer.BarkerMH`

`BarkerMH(model=..., potential_fn=..., init_strategy=...)` returns a kernel accepted by `MCMC`. `model` is a model callable, `potential_fn` is a numerical scalar-valued callable on latent coordinates, and `init_strategy` is an initialization callable.

## `velnora.infer.CustomGibbs`

`CustomGibbs(gibbs_fn)` returns a kernel accepted by `MCMC`. `gibbs_fn(rng_key, gibbs_sites, hmc_sites)` receives two string-to-array site mappings and returns a string-to-array mapping for the updated sites.

Rejected block specifications or callback results raise `ValueError`.

## `velnora.contrib.tfp.distributions.TFPDistribution`

`TFPDistribution[distribution_class](*args, **kwargs)` accepts an external TensorFlow Probability distribution class and that class’s constructor arguments. It returns a distribution wrapper exposing `log_prob(value)` as a numerical array. External TensorFlow Probability distribution instances are also accepted by `velnora.sample`.

## `velnora.infer.gibbs.discrete_latent_sites`

`discrete_latent_sites(model_trace)` accepts an execution-record mapping and returns a sequence of string site names. It can be passed directly as a block site-selector callable.

## `velnora.infer.MCMC`

`MCMC(sampler, *, num_warmup, num_samples, num_chains=..., thinning=..., chain_method=..., progress_bar=...)` accepts a kernel object, integer collection arguments, a string chain mode, and a boolean progress option.

`run(rng_key, *args, extra_fields=..., init_params=..., **kwargs)` and `warmup(rng_key, *args, extra_fields=..., init_params=..., collect_warmup=..., **kwargs)` accept model arguments. `init_params` accepts a numerical latent-coordinate array or mapping, with a leading chain axis for multiple chains. `extra_fields` is a sequence of string field names. `collect_warmup` is boolean.

`get_samples(group_by_chain=...)` returns a mapping from model site names to numerical arrays. With a potential callable in place of a model it returns the original numerical latent structure. Grouped arrays have chain and retained-draw axes followed by parameter axes; flattened arrays combine chain and retained-draw axes.

`get_extra_fields(group_by_chain=...)` returns a mapping of requested diagnostic names to aligned arrays. `potential_energy` holds numerical energies, `accept_prob` numerical acceptance probabilities, `diverging` boolean divergence indicators, and `z.batch` integer data-index arrays. `group_by_chain` is boolean and uses the same grouping convention as sample retrieval.

`post_warmup_state` is a readable and assignable reusable sampler state or `None`. `last_state` is the final reusable state. Rejected collection or missing-initialization requests raise `ValueError`.

The `chain_method` selections are `"sequential"` for separate CPU chains and `"vectorized"` for jointly batched CPU chains.

Omitting `group_by_chain` selects the flattened sample and diagnostic forms.

## `velnora.infer.AIES`

`AIES(model=..., potential_fn=..., moves=..., init_strategy=...)` returns a kernel accepted by `MCMC`. `model` is a model callable, `potential_fn` is a numerical scalar-valued callable on latent coordinates, and `init_strategy` is an initialization callable.

`StretchMove()` returns a move usable as a key in the `moves` mapping; mapping values are numerical weights. Rejected ensemble requests raise `AssertionError` or `ValueError`.

## `velnora.infer.Gibbs`

`Gibbs(blocks)` returns a kernel accepted by `MCMC`. `blocks` is a sequence of `(kernel, sites)` pairs; `sites` is a sequence of site-name strings, a site-selector callable receiving an execution mapping, or `None`.

Rejected block specifications or callback results raise `ValueError`.

## `velnora.infer.HMCECS`

`HMCECS(inner_kernel, *, proxy=...)` returns a kernel accepted by `MCMC`. `proxy` is a proxy constructor.

## `velnora.infer.HMCGibbs`

`HMCGibbs(inner_kernel, gibbs_fn, gibbs_sites)` returns a kernel accepted by `MCMC`. `gibbs_fn(rng_key, gibbs_sites, hmc_sites)` receives site mappings and returns an updated-site mapping; `gibbs_sites` is a sequence of site-name strings.

## `velnora.infer.SA`

`SA(model=..., potential_fn=..., init_strategy=...)` returns a kernel accepted by `MCMC`. `model` is a model callable, `potential_fn` is a numerical scalar-valued callable on latent coordinates, and `init_strategy` is an initialization callable.

## `velnora.contrib.tfp.mcmc.HamiltonianMonteCarlo`

`HamiltonianMonteCarlo(model, *, step_size=..., num_leapfrog_steps=...)` accepts a model callable, a numerical step size and an integer leapfrog count. It returns a kernel accepted by `MCMC`.

## `velnora.infer.Predictive`

`Predictive(model, posterior_samples=..., *, guide=..., params=..., num_samples=..., return_sites=..., infer_discrete=..., batch_ndims=..., condition_deterministic=...)` returns a callable accepting `(rng_key, *args, **kwargs)` with the model’s call inputs.

`posterior_samples` and `params` are string-to-array mappings; `guide` is callable; `num_samples` and `batch_ndims` are integers; `return_sites` is a sequence of site-name strings; `infer_discrete` and `condition_deterministic` are booleans.

Calling the predictive object returns a mapping from site-name strings to numerical sample arrays. Each value carries the designated leading posterior-sample axes followed by that site’s batch and event axes. Rejected prediction requests raise `ValueError`. Prediction diagnostics use Python `UserWarning` warnings.

## `velnora.infer.log_likelihood`

`log_likelihood(model, posterior_samples, *args, parallel=..., batch_ndims=..., **kwargs)` accepts a model callable, a site-name-to-array posterior mapping, model call inputs, a boolean `parallel` option, and integer `batch_ndims`.

Returns a mapping from observed-site names to numerical log-likelihood arrays, with designated posterior-sample axes followed by independent observation-batch axes.

## `velnora.diagnostics.autocorrelation`

`autocorrelation(x, axis=..., bias=...)`. `x` is a numerical array. `axis` is an integer. `bias` is boolean.

Returns a numerical array with the input shape; the selected sample axis indexes lags in the result.

## `velnora.diagnostics.autocovariance`

`autocovariance(x, axis=..., bias=...)`. `x` is a numerical array. `axis` is an integer. `bias` is boolean.

Returns a numerical array with the input shape; the selected sample axis indexes lags in the result.

## `velnora.diagnostics.effective_sample_size`

`effective_sample_size(x, bias=...)`. `x` is a numerical array. `bias` is boolean.

Input axes are chain, draw, then parameter components. Returns a numerical array with the component shape. Rejected chain or draw prerequisites raise `AssertionError`.

## `velnora.diagnostics.gelman_rubin`

`gelman_rubin(x)`. `x` is a numerical array.

Input axes are chain, draw, then parameter components. Returns a numerical array with the component shape. Rejected chain or draw prerequisites raise `AssertionError`.

## `velnora.diagnostics.split_gelman_rubin`

`split_gelman_rubin(x)`. `x` is a numerical array.

Input axes are chain, draw, then parameter components. Returns a numerical array with the component shape. Rejected chain or draw prerequisites raise `AssertionError`.

## `velnora.diagnostics.hpdi`

`hpdi(x, prob=..., axis=...)`. `x` is a numerical array. `axis` is an integer. `prob` is numerical.

Returns a numerical array with the selected sample axis replaced by an endpoint axis of length two: lower endpoint first, upper endpoint second.

## `velnora.diagnostics.summary`

`summary(samples, prob=..., group_by_chain=...)` accepts a mapping from parameter names to numerical sample arrays, numerical `prob` and boolean `group_by_chain`. Grouped arrays start with chain and draw axes; ungrouped arrays start with a draw axis.

Returns a nested mapping `{<parameter>: {<statistic>: <array>}}`. The fields `mean`, `std`, `median`, `n_eff`, and `r_hat` carry the mean, sample standard deviation, median, effective sample size, and split convergence measure. Each numerical array has the parameter’s component shape.

The lower and upper interval endpoint keys are `f"{50*(1-prob):.1f}%"` and `f"{50*(1+prob):.1f}%"`, respectively: tail percentages printed with one fractional digit and `%`. Their values have the parameter’s component shape.

Omitting `group_by_chain` selects the grouped input form.

## `velnora.diagnostics.print_summary`

`print_summary(samples)` accepts a parameter-name-to-sample-array mapping and writes a whitespace-separated table to `stdout`.

The header columns are `mean std median 5.0% 95.0% n_eff r_hat`. Each data row begins with the parameter name, followed by those seven numerical columns printed with at least two fractional digits. Array components use the naming form `<parameter>[<index>,<index>,...]` with zero-based decimal indices.

## `velnora.infer.hmc_util.consensus`

`consensus(subposteriors, diagonal=..., rng_key=...)`. `subposteriors` is a sequence of mappings from site names to sample arrays; `diagonal` is boolean and `rng_key` a random key.

Returns a mapping from site-name strings to numerical sample arrays with a leading draw axis and original site dimensions.

## `velnora.infer.hmc_util.parametric`

`parametric(subposteriors, diagonal=...)`. `subposteriors` is a sequence of mappings from site names to sample arrays; `diagonal` is boolean.

Returns `(mean, covariance)` in flattened parameter coordinates. `mean` is a numerical vector; `covariance` is a numerical square matrix, or a variance vector for diagonal output.

## `velnora.infer.hmc_util.parametric_draws`

`parametric_draws(subposteriors, num_draws, diagonal=..., rng_key=...)`. `subposteriors` is a sequence of mappings from site names to sample arrays; `diagonal` is boolean and `rng_key` a random key.

Returns a mapping from site-name strings to numerical sample arrays with a leading draw axis and original site dimensions.

## `velnora.infer.importance.psis_diagnostic`

`psis_diagnostic(rng_key, param_map, model, guide, *args, num_particles=..., **kwargs)` accepts a fitted-parameter mapping, model and guide callables, their call inputs, and an integer particle count. Returns a scalar numerical Pareto tail diagnostic. Rejected requests raise `ValueError`; diagnostic warnings use `UserWarning`.

## `velnora.infer.calibration.vsbc_diagnostic`

`vsbc_diagnostic(rng_key, model, guide, optim, loss, *args, observed_sites=..., simulated_data_to_args=..., num_simulations=..., num_svi_steps=..., num_samples=..., **kwargs)` accepts a legacy random-key array, model and guide callables, an optimizer, an objective, and model call inputs. Count arguments are integers; `observed_sites` is a sequence of string site names or `None`.

`simulated_data_to_args(sim_data, *args, **kwargs)` receives a mapping of simulated site values and returns `(positional_args, keyword_args)`, a tuple or list of positional arguments and a keyword mapping.

Returns an object with `param_names` (a sequence of latent-site names), `ranks` and `probabilities` (mappings from names to numerical arrays with simulation and component axes), and `ks_stats` and `ks_pvalues` (mappings from names to component-shaped numerical arrays). These carry component ranks, calibration probabilities, and symmetry-assessment statistics and p-values. Rejected calibration requests raise `ValueError`.

## `velnora.infer.inspect.get_dependencies`

`get_dependencies(model, model_args=..., model_kwargs=...)` accepts a callable, a positional argument tuple and a keyword mapping.

Returns a dictionary with `prior_dependencies` and `posterior_dependencies`. Each is a mapping from a site-name string to a mapping of related site-name strings to sets of independent-group names.

## `velnora.infer.inspect.get_model_relations`

`get_model_relations(model, model_args=...)` accepts a model callable and a positional input tuple.

Returns a dictionary. `sample_sample` and `sample_param` map random-site names to lists of related random-site or parameter names. `sample_dist` maps random-site names to family strings, including `Normal` and `LogNormal`. `param_constraint` maps parameter names to constraint descriptions. A constrained parameter carries the string returned by its public constraint object; an unconstrained real parameter carries either that object's string or the empty string. `plate_sample` maps independent-group names to lists of site names. `observed` is a list of observed-site names.

## `velnora.infer.inspect.render_model`

`render_model(model, model_args=..., filename=..., render_params=..., render_distributions=...)` accepts a model callable, input tuple, optional string output path, and boolean rendering options. Returns a graph object with a string `source` attribute containing directed DOT. A supplied SVG filename receives an SVG image.

DOT node identifiers are site names; directed edges connect source and target identifiers. Independent groups appear as cluster subgraphs with group labels and member nodes. Random-site nodes expose a `fillcolor` attribute for observation status.

Distribution annotations appear in the node `distribution_description_node` with a `label` containing records `<site> ~ <family>` and, when parameter annotations are included, `<parameter> ∈ <constraint>`, separated by `\l` line breaks.

The SVG document uses the namespace `http://www.w3.org/2000/svg`. Its `g` elements with `class` values `node`, `edge`, and `cluster` contain `title` children carrying a site name, `<source>-><target>`, or `cluster_<group>`, respectively. `text` elements carry site and group names and annotation records; random-site graphical elements expose `fill` attributes.

## `velnora.util.format_shapes`

`format_shapes(trace, compute_log_prob=...)` accepts an execution-record mapping and a boolean or a predicate receiving a site record with `name`. Returns a text report.

The first line is `Trace Shapes:`. Section markers are `Param Sites:` and `Sample Sites:`. A random site starts with `<site> dist <batch dimensions> | <event dimensions>`, followed by `value <non-event dimensions> | <event dimensions>` and, when included, `log_prob <dimensions> |`. Independent-group rows have the form `<plate> plate <dimensions> |`. Dimensions are whitespace-separated decimal integers; an empty dimension sequence represents a scalar.

## `velnora.contrib.module.flax_module`

`flax_module(name, nn_module, *args, input_shape=..., apply_rng=..., mutable=..., **kwargs)` accepts a string registration name and a caller-owned network object. It returns a callable accepting that network’s numerical inputs and call options and returning its numerical output structure.

`input_shape` is an integer tuple, `apply_rng` a sequence of randomness-collection names, and `mutable` a sequence of state-collection names where supplied. The returned callable accepts `rngs` as a mapping from collection names to random keys.

## `velnora.contrib.module.nnx_module`

`nnx_module(name, nn_module)` accepts a string registration name and a caller-owned network object. It returns a callable accepting that network’s numerical inputs and call options and returning its numerical output structure.

The returned callable accepts `rngs` as a caller-supplied NNX randomness object.

## `velnora.contrib.module.eqx_module`

`eqx_module(name, nn_module)` accepts a string registration name and a caller-owned network object. It returns a callable accepting that network’s numerical inputs and call options and returning its numerical output structure.

The returned callable accepts the caller network’s `key` keyword when supplied.

## `velnora.contrib.module.random_flax_module`

`random_flax_module(name, nn_module, prior, *args, input_shape=..., apply_rng=..., mutable=..., **kwargs)` accepts a string registration name and a caller-owned network object. It returns a callable accepting that network’s numerical inputs and call options and returning its numerical output structure.

`input_shape` is an integer tuple, `apply_rng` a sequence of randomness-collection names, and `mutable` a sequence of state-collection names where supplied. The returned callable accepts `rngs` as a mapping from collection names to random keys.

`prior` is a distribution, a mapping from network-parameter names to distributions, or `prior(name, shape)` returning a distribution. Registered latent names have the form `<registration>/<parameter>`, using parameter names supplied by the network.

## `velnora.contrib.module.random_nnx_module`

`random_nnx_module(name, nn_module, prior)` accepts a string registration name and a caller-owned network object. It returns a callable accepting that network’s numerical inputs and call options and returning its numerical output structure.

The returned callable accepts `rngs` as a caller-supplied NNX randomness object.

`prior` is a distribution, a mapping from network-parameter names to distributions, or `prior(name, shape)` returning a distribution. Registered latent names have the form `<registration>/<parameter>`, using parameter names supplied by the network.

## `velnora.contrib.module.random_eqx_module`

`random_eqx_module(name, nn_module, prior)` accepts a string registration name and a caller-owned network object. It returns a callable accepting that network’s numerical inputs and call options and returning its numerical output structure.

The returned callable accepts the caller network’s `key` keyword when supplied.

`prior` is a distribution, a mapping from network-parameter names to distributions, or `prior(name, shape)` returning a distribution. Registered latent names have the form `<registration>/<parameter>`, using parameter names supplied by the network.

## `velnora.contrib.einstein.SVGD`

`SVGD(model, optim, kernel_fn, num_stein_particles=..., **static_kwargs)` returns a particle-inference object. `model` is callable; `optim` and `kernel_fn` are objects. `num_stein_particles` are integers.

`init(rng_key, *args, **kwargs)` returns a reusable state. `get_params(state)` returns a constrained parameter mapping. `evaluate(state, *args, **kwargs)` returns a scalar numerical diagnostic. `update(state, *args, **kwargs)` returns `(next_state, diagnostic)` with the same diagnostic form.

`run(rng_key, num_steps, *args, progress_bar=..., **kwargs)` returns an object with `params` (a parameter mapping), `state` (reusable state), and `losses` (a numerical diagnostic-history array of length `num_steps`). Guide particle parameter arrays have a leading particle axis; shared model parameters have their ordinary shape.

## `velnora.contrib.einstein.ASVGD`

`ASVGD(model, optim, kernel_fn, num_stein_particles=..., num_cycles=..., transition_speed=..., **static_kwargs)` returns a particle-inference object. `model` is callable; `optim` and `kernel_fn` are objects. `num_stein_particles`, `num_cycles` are integers. `transition_speed` is numerical.

`init(rng_key, num_steps, *args, **kwargs)` returns a reusable state. `get_params(state)` returns a constrained parameter mapping. `evaluate(state, *args, **kwargs)` returns a scalar numerical diagnostic. `update(state, *args, **kwargs)` returns `(next_state, diagnostic)` with the same diagnostic form.

`run(rng_key, num_steps, *args, progress_bar=..., init_state=..., **kwargs)` returns an object with `params` (a parameter mapping), `state` (reusable state), and `losses` (a numerical diagnostic-history array of length `num_steps`). Guide particle parameter arrays have a leading particle axis; shared model parameters have their ordinary shape.

Rejected particle-inference requests raise `AssertionError`.

## `velnora.contrib.einstein.SteinVI`

`SteinVI(model, guide, optim, kernel_fn, num_stein_particles=..., num_elbo_particles=..., **static_kwargs)` returns a particle-inference object. `model` is callable; `optim` and `kernel_fn` are objects. `guide` is callable. `num_stein_particles`, `num_elbo_particles` are integers.

`init(rng_key, *args, **kwargs)` returns a reusable state. `get_params(state)` returns a constrained parameter mapping. `evaluate(state, *args, **kwargs)` returns a scalar numerical diagnostic. `update(state, *args, **kwargs)` returns `(next_state, diagnostic)` with the same diagnostic form.

`run(rng_key, num_steps, *args, progress_bar=..., **kwargs)` returns an object with `params` (a parameter mapping), `state` (reusable state), and `losses` (a numerical diagnostic-history array of length `num_steps`). Guide particle parameter arrays have a leading particle axis; shared model parameters have their ordinary shape.

Rejected particle-inference requests raise `AssertionError`.

## `velnora.contrib.einstein.MixtureGuidePredictive`

`MixtureGuidePredictive(model, guide, params, *, guide_sites=..., num_samples=..., return_sites=...)` accepts callable model and guide, a fitted-parameter mapping, parameter-name and return-site sequences, and an integer draw count. Calling the result with `(rng_key, *args, **kwargs)` returns a mapping from site names to numerical arrays with a leading draw axis.

The returned `mixture_assignments` field is an integer array with one component index per draw. Component-guide parameters in `params` have a leading component axis; shared parameters keep their ordinary shapes.

## `velnora.contrib.einstein.RBFKernel`

`RBFKernel(mode=..., matrix_mode=..., bandwidth_factor=...)` returns a kernel object.

`init(rng_key, particles_shape)` accepts a random key and integer particle-array shape. `compute(rng_key, particles, particle_info, loss_fn)` returns a callable `kernel(x, y)`. `particles` is a numerical array with particle and coordinate axes; `particle_info` maps parameter or group names to `(start, end)` coordinate slices with an exclusive end; `x` and `y` are numerical coordinate vectors.

The returned callable produces a numerical scalar, coordinate vector, or square coordinate matrix according to the selected output form. `mode` and `matrix_mode` are string selectors; `bandwidth_factor` is a callable receiving the particle count.

The `mode` selections are `"norm"` for a scalar, `"vector"` for a coordinate vector, and `"matrix"` for a square coordinate matrix. The `matrix_mode` selections are `"norm_diag"` for a repeated scalar diagonal and `"vector_diag"` for a coordinatewise diagonal.

## `velnora.contrib.einstein.IMQKernel`

`IMQKernel(mode=..., const=..., expon=...)` returns a kernel object.

`init(rng_key, particles_shape)` accepts a random key and integer particle-array shape. `compute(rng_key, particles, particle_info, loss_fn)` returns a callable `kernel(x, y)`. `particles` is a numerical array with particle and coordinate axes; `particle_info` maps parameter or group names to `(start, end)` coordinate slices with an exclusive end; `x` and `y` are numerical coordinate vectors.

The returned callable produces a numerical scalar or coordinate vector according to the selected output form. `mode` is a string selector; `const` and `expon` are numerical.

Rejected kernel specifications raise `AssertionError`.

The `mode` selections are `"norm"` for a scalar and `"vector"` for a coordinate vector.

## `velnora.contrib.einstein.LinearKernel`

`LinearKernel()` returns a kernel object.

`init(rng_key, particles_shape)` accepts a random key and integer particle-array shape. `compute(rng_key, particles, particle_info, loss_fn)` returns a callable `kernel(x, y)`. `particles` is a numerical array with particle and coordinate axes; `particle_info` maps parameter or group names to `(start, end)` coordinate slices with an exclusive end; `x` and `y` are numerical coordinate vectors.

The returned callable produces a numerical scalar.

## `velnora.contrib.einstein.MixtureKernel`

`MixtureKernel(ws, kernel_fns, mode=...)` returns a kernel object.

`init(rng_key, particles_shape)` accepts a random key and integer particle-array shape. `compute(rng_key, particles, particle_info, loss_fn)` returns a callable `kernel(x, y)`. `particles` is a numerical array with particle and coordinate axes; `particle_info` maps parameter or group names to `(start, end)` coordinate slices with an exclusive end; `x` and `y` are numerical coordinate vectors.

The returned callable produces a numerical scalar, coordinate vector, or square coordinate matrix according to the selected output form. `mode` is a string selector; `ws` is a numerical weight sequence and `kernel_fns` is a sequence of kernel objects.

Rejected kernel specifications raise `AssertionError`.

The `mode` selections are `"norm"` for a scalar, `"vector"` for a coordinate vector, and `"matrix"` for a square coordinate matrix.

## `velnora.contrib.einstein.GraphicalKernel`

`GraphicalKernel(local_kernel_fns=..., default_kernel_fn=...)` returns a kernel object.

`init(rng_key, particles_shape)` accepts a random key and integer particle-array shape. `compute(rng_key, particles, particle_info, loss_fn)` returns a callable `kernel(x, y)`. `particles` is a numerical array with particle and coordinate axes; `particle_info` maps parameter or group names to `(start, end)` coordinate slices with an exclusive end; `x` and `y` are numerical coordinate vectors.

`local_kernel_fns` maps group names to kernel objects; `default_kernel_fn` is a kernel object. The returned callable produces a numerical square matrix in the supplied group-coordinate packing.

## `velnora.contrib.einstein.ProbabilityProductKernel`

`ProbabilityProductKernel(guide, scale=...)` returns a kernel object.

`init(rng_key, particles_shape)` accepts a random key and integer particle-array shape. `compute(rng_key, particles, particle_info, loss_fn)` returns a callable `kernel(x, y)`. `particles` is a numerical array with particle and coordinate axes; `particle_info` maps parameter or group names to `(start, end)` coordinate slices with an exclusive end; `x` and `y` are numerical coordinate vectors.

The returned callable produces a numerical scalar.

Rejected kernel specifications raise `AssertionError`.

## `velnora.contrib.einstein.RandomFeatureKernel`

`RandomFeatureKernel(bandwidth_subset=...)` returns a kernel object.

`init(rng_key, particles_shape)` accepts a random key and integer particle-array shape. `compute(rng_key, particles, particle_info, loss_fn)` returns a callable `kernel(x, y)`. `particles` is a numerical array with particle and coordinate axes; `particle_info` maps parameter or group names to `(start, end)` coordinate slices with an exclusive end; `x` and `y` are numerical coordinate vectors.

The returned callable produces a numerical scalar.

`bandwidth_subset` is an integer or `None`. Missing initialization raises `RuntimeError`; incompatible particle shapes raise `ValueError`.

## `velnora.contrib.einstein.stein_kernels.RadialGaussNewtonKernel`

`RadialGaussNewtonKernel()` returns a kernel object.

`init(rng_key, particles_shape)` accepts a random key and integer particle-array shape. `compute(rng_key, particles, particle_info, loss_fn)` returns a callable `kernel(x, y)`. `particles` is a numerical array with particle and coordinate axes; `particle_info` maps parameter or group names to `(start, end)` coordinate slices with an exclusive end; `x` and `y` are numerical coordinate vectors.

The returned callable produces a numerical scalar.

`loss_fn(rng_key, coordinate, particle_index)` returns a differentiable numerical scalar.

## `velnora.contrib.stochastic_support.dcc.DCC`

`DCC(model, mcmc_kwargs, num_slp_samples=..., max_slps=...)` accepts a model callable, an MCMC-options mapping, and integer exploration and path-cap arguments. Supported `mcmc_kwargs` keys are `num_warmup`, `num_samples`, `num_chains`, and `progress_bar`.

`run(rng_key, *args, **kwargs)` accepts model call inputs and returns an object with `samples` and `slp_weights`. `samples` maps path keys to site-name-to-array sample mappings; arrays have a leading posterior-draw axis and site dimensions. `slp_weights` maps the same keys to scalar numerical path weights.

Path keys are strings of decimal branching decisions. Unsupported branching raises `RuntimeError`.

## `velnora.contrib.stochastic_support.sdvi.SDVI`

`SDVI(model, optimizer, svi_num_steps=..., combine_elbo_particles=..., guide_init=..., loss=..., num_slp_samples=..., max_slps=...)` accepts a model callable, optimizer object, integer work and path-count arguments, a guide constructor, and an objective object.

`run(rng_key, *args, **kwargs)` accepts model call inputs and returns an object with `guides` and `slp_weights`. `guides` maps path keys to `(guide, params)` pairs; `params` is a fitted-parameter mapping. `slp_weights` maps the same path keys to scalar numerical path weights.

Path keys are strings of decimal branching decisions. Unsupported branching raises `RuntimeError`; rejected objective specifications raise `ValueError`.

## `velnora.contrib.hsgp.approximation.hsgp_squared_exponential`

`hsgp_squared_exponential(x, alpha, length, ell, m, non_centered=...)`. Numerical parameters accept scalars or numerical arrays. `x` contains input locations. `ell` contains domain widths. `m` is an integer or a sequence of integer retained counts. `non_centered` is boolean.

Returns a real numerical array of function values, with a location axis.

Rejected specifications raise `ValueError`.

## `velnora.contrib.hsgp.approximation.hsgp_matern`

`hsgp_matern(x, nu, alpha, length, ell, m, non_centered=...)`. Numerical parameters accept scalars or numerical arrays. `x` contains input locations. `ell` contains domain widths. `m` is an integer or a sequence of integer retained counts. `non_centered` is boolean.

Returns a real numerical array of function values, with a location axis.

Rejected specifications raise `ValueError`.

## `velnora.contrib.hsgp.approximation.hsgp_rational_quadratic`

`hsgp_rational_quadratic(x, alpha, length, scale_mixture, ell, m, non_centered=...)`. Numerical parameters accept scalars or numerical arrays. `x` contains input locations. `ell` contains domain widths. `m` is an integer or a sequence of integer retained counts. `non_centered` is boolean.

Returns a real numerical array of function values, with a location axis.

## `velnora.contrib.hsgp.approximation.hsgp_periodic_non_centered`

`hsgp_periodic_non_centered(x, alpha, length, w0, m)`. Numerical parameters accept scalars or numerical arrays. `x` contains input locations. `w0` is a numerical frequency. `m` is an integer or a sequence of integer retained counts.

Returns a real numerical array of function values, with a location axis.

## `velnora.contrib.hsgp.laplacian.eigenindices`

`eigenindices(m, dim)`. Numerical parameters accept scalars or numerical arrays. `m` is an integer or a sequence of integer retained counts. `dim` is the integer input dimension.

Returns an integer array with shape `(dim, <number of basis terms>)`; each column identifies one basis term.

## `velnora.contrib.hsgp.laplacian.sqrt_eigenvalues`

`sqrt_eigenvalues(ell, m, dim)`. Numerical parameters accept scalars or numerical arrays. `ell` contains domain widths. `m` is an integer or a sequence of integer retained counts. `dim` is the integer input dimension.

Returns a numerical frequency array with shape `(dim, <number of basis terms>)`, with columns aligned to `eigenindices`.

## `velnora.contrib.hsgp.laplacian.eigenfunctions`

`eigenfunctions(x, ell, m)`. Numerical parameters accept scalars or numerical arrays. `x` contains input locations. `ell` contains domain widths. `m` is an integer or a sequence of integer retained counts.

Returns a numerical array with location axes followed by a basis-term axis, aligned to `eigenindices`. Rejected specifications raise `ValueError`.

## `velnora.contrib.hsgp.laplacian.eigenfunctions_periodic`

`eigenfunctions_periodic(x, w0, m)`. Numerical parameters accept scalars or numerical arrays. `x` contains input locations. `w0` is a numerical frequency. `m` is an integer or a sequence of integer retained counts.

Returns `(cosines, sines)`, two real numerical arrays with location and retained-term axes. Rejected specifications raise `ValueError`.

## `velnora.contrib.hsgp.spectral_densities.spectral_density_squared_exponential`

`spectral_density_squared_exponential(dim, w, alpha, length)`. Numerical parameters accept scalars or numerical arrays. `w` contains frequencies. `dim` is the integer input dimension.

Returns a numerical scalar spectral density for the supplied frequency vector.

## `velnora.contrib.hsgp.spectral_densities.spectral_density_matern`

`spectral_density_matern(dim, nu, w, alpha, length)`. Numerical parameters accept scalars or numerical arrays. `w` contains frequencies. `dim` is the integer input dimension.

Returns a numerical scalar spectral density for the supplied frequency vector.

## `velnora.contrib.hsgp.spectral_densities.spectral_density_rational_quadratic`

`spectral_density_rational_quadratic(dim, w, alpha, length, scale_mixture)`. Numerical parameters accept scalars or numerical arrays. `w` contains frequencies. `dim` is the integer input dimension.

Returns a numerical scalar spectral density for the supplied frequency vector.

## `velnora.contrib.hsgp.spectral_densities.diag_spectral_density_squared_exponential`

`diag_spectral_density_squared_exponential(alpha, length, ell, m, dim)`. Numerical parameters accept scalars or numerical arrays. `ell` contains domain widths. `m` is an integer or a sequence of integer retained counts. `dim` is the integer input dimension.

Returns a real numerical vector of spectral weights, with entries aligned to the corresponding public basis terms.

## `velnora.contrib.hsgp.spectral_densities.diag_spectral_density_matern`

`diag_spectral_density_matern(nu, alpha, length, ell, m, dim)`. Numerical parameters accept scalars or numerical arrays. `ell` contains domain widths. `m` is an integer or a sequence of integer retained counts. `dim` is the integer input dimension.

Returns a real numerical vector of spectral weights, with entries aligned to the corresponding public basis terms.

## `velnora.contrib.hsgp.spectral_densities.diag_spectral_density_rational_quadratic`

`diag_spectral_density_rational_quadratic(alpha, length, scale_mixture, ell, m, dim)`. Numerical parameters accept scalars or numerical arrays. `ell` contains domain widths. `m` is an integer or a sequence of integer retained counts. `dim` is the integer input dimension.

Returns a real numerical vector of spectral weights, with entries aligned to the corresponding public basis terms.

## `velnora.contrib.hsgp.spectral_densities.diag_spectral_density_periodic`

`diag_spectral_density_periodic(alpha, length, m)`. Numerical parameters accept scalars or numerical arrays. `m` is an integer or a sequence of integer retained counts.

Returns a real numerical vector of spectral weights, with entries aligned to the corresponding public basis terms.

## `velnora.contrib.nested_sampling.NestedSampler`

`NestedSampler(model, *, constructor_kwargs=..., termination_kwargs=...)` accepts a model callable and option mappings. Supported constructor-option keys are `num_live_points` and `max_samples`; the supported termination-option key is `dlogZ`. These options accept numerical values.

`run(rng_key, *args, **kwargs)` accepts model call inputs. `get_weighted_samples()` returns `(samples, log_weights)`: a site-name-to-array mapping and an aligned one-dimensional numerical log-weight array. Sample arrays have a leading weighted-point axis followed by original site dimensions.

`get_samples(rng_key, num_samples, *, group_by_chain=...)` returns a mapping from original site names to numerical arrays, with a leading requested-draw axis. Boolean `group_by_chain` selects an additional leading singleton chain axis.

`print_summary()` writes to `stdout`. Readable lines have the forms `logZ=<estimate> +- <uncertainty>`, `samples: <integer>`, `likelihood evals: <integer>`, and `ESS=<number>`. `logZ` carries the log-evidence estimate, `samples` the completed-run sample count, `likelihood evals` the likelihood-evaluation count, and `ESS` an effective-sample-size diagnostic.

`diagnostics()` produces numerical diagnostic figures accessible through `matplotlib.pyplot`. Figure axes expose numerical line data and posterior marginal histogram rectangles with position, width, and height. A marginal’s x-axis label is its site name.

`get_samples`, `get_weighted_samples`, `print_summary`, and `diagnostics` raise `RuntimeError` when results are unavailable.

## `velnora.util`

The module `velnora.util` exposes `format_shapes`.

## `velnora.primitives`

The module `velnora.primitives` exposes `mutable`.

## `velnora.optim`

The module `velnora.optim` exposes `Adagrad`, `Adam`, `ClippedAdam`, `Minimize`, `Momentum`, `RMSProp`, `RMSPropMomentum`, `SGD`, `SM3`, `optax_to_velnora`.

## `velnora.ops.indexing`

The module `velnora.ops.indexing` exposes `Vindex`.

## `velnora.nn`

The module `velnora.nn` exposes `AutoregressiveNN`, `BlockNeuralAutoregressiveNN`.

## `velnora.infer.util`

The module `velnora.infer.util` exposes `compute_log_probs`, `constrain_fn`, `find_valid_initial_params`, `initialize_model`, `log_density`, `potential_energy`, `unconstrain_fn`.

## `velnora.infer.reparam`

The module `velnora.infer.reparam` exposes `CircularReparam`, `DiscreteCosineReparam`, `ExplicitReparam`, `HaarReparam`, `LocScaleReparam`, `NeuTraReparam`, `ProjectedNormalReparam`, `TransformReparam`, `UnitJacobianReparam`.

## `velnora.infer.inspect`

The module `velnora.infer.inspect` exposes `get_dependencies`, `get_model_relations`, `render_model`.

## `velnora.infer.initialization`

The module `velnora.infer.initialization` exposes `init_to_feasible`, `init_to_mean`, `init_to_median`, `init_to_sample`, `init_to_uniform`, `init_to_value`.

## `velnora.infer.importance`

The module `velnora.infer.importance` exposes `psis_diagnostic`.

## `velnora.infer.hmc_util`

The module `velnora.infer.hmc_util` exposes `consensus`, `parametric`, `parametric_draws`.

## `velnora.infer.gibbs`

The module `velnora.infer.gibbs` exposes `discrete_latent_sites`.

## `velnora.infer.calibration`

The module `velnora.infer.calibration` exposes `vsbc_diagnostic`.

## `velnora.infer.autoguide`

The module `velnora.infer.autoguide` exposes `AutoBNAFNormal`, `AutoBatchedLowRankMultivariateNormal`, `AutoBatchedMultivariateNormal`, `AutoDAIS`, `AutoDelta`, `AutoDiagonalNormal`, `AutoGuideList`, `AutoIAFNormal`, `AutoLaplaceApproximation`, `AutoLowRankMultivariateNormal`, `AutoMultivariateNormal`, `AutoNormal`, `AutoSemiDAIS`, `AutoSurrogateLikelihoodDAIS`.

## `velnora.infer`

The module `velnora.infer` exposes `AIES`, `BarkerMH`, `CustomGibbs`, `DiscreteGibbs`, `DiscreteHMCGibbs`, `ESS`, `Gibbs`, `HMC`, `HMCECS`, `HMCGibbs`, `MCMC`, `MixedHMC`, `NUTS`, `Predictive`, `RenyiELBO`, `SA`, `SVI`, `TraceEnum_ELBO`, `TraceGraph_ELBO`, `TraceMeanField_ELBO`, `Trace_ELBO`, `autoguide`, `calibration`, `gibbs`, `hmc_util`, `importance`, `init_to_feasible`, `init_to_uniform`, `init_to_value`, `initialization`, `inspect`, `log_likelihood`, `reparam`, `util`.

## `velnora.handlers`

The module `velnora.handlers` exposes `block`, `collapse`, `condition`, `do`, `infer_config`, `lift`, `mask`, `reparam`, `replay`, `scale`, `scope`, `seed`, `substitute`, `trace`, `uncondition`.

## `velnora.distributions.transforms`

The module `velnora.distributions.transforms` exposes `AbsTransform`, `AffineTransform`, `CatTransform`, `CholeskyTransform`, `ComplexTransform`, `ComposeTransform`, `CorrCholeskyTransform`, `CorrMatrixCholeskyTransform`, `DiscreteCosineTransform`, `ExpTransform`, `HaarTransform`, `IdentityTransform`, `IndependentTransform`, `L1BallTransform`, `LowerCholeskyAffine`, `LowerCholeskyTransform`, `OrderedTransform`, `PackRealFastFourierCoefficientsTransform`, `PermuteTransform`, `PowerTransform`, `RealFastFourierTransform`, `RecursiveLinearTransform`, `ReshapeTransform`, `ScaledUnitLowerCholeskyTransform`, `SigmoidTransform`, `SimplexToOrderedTransform`, `SoftplusLowerCholeskyTransform`, `SoftplusTransform`, `StickBreakingTransform`, `UnpackTransform`, `ZeroSumTransform`, `biject_to`.

## `velnora.distributions.flows`

The module `velnora.distributions.flows` exposes `BlockNeuralAutoregressiveTransform`, `InverseAutoregressiveTransform`.

## `velnora.distributions.constraints`

The module `velnora.distributions.constraints` exposes `boolean`, `cat`, `circular`, `complex`, `corr_cholesky`, `corr_matrix`, `dependent`, `extended_real`, `greater_than`, `greater_than_eq`, `independent`, `integer_greater_than`, `integer_interval`, `interval`, `l1_ball`, `less_than`, `lower_cholesky`, `multinomial`, `nonnegative`, `nonnegative_integer`, `open_interval`, `ordered_vector`, `positive`, `positive_definite`, `positive_integer`, `positive_ordered_vector`, `positive_semidefinite`, `real`, `real_matrix`, `real_vector`, `scaled_unit_lower_cholesky`, `simplex`, `softmax_logits`, `sphere`, `unit_interval`, `zero_sum`.

A constraint object's string conversion returns its textual domain description, including any numerical bounds.

## `velnora.distributions`

The module `velnora.distributions` exposes `AsymmetricLaplace`, `AsymmetricLaplaceQuantile`, `Bernoulli`, `Beta`, `BetaBinomial`, `BetaNegativeBinomial`, `BetaProportion`, `Binomial`, `CAR`, `Categorical`, `Cauchy`, `Chi2`, `CirculantNormal`, `Dagum`, `Delta`, `Dirichlet`, `DirichletMultinomial`, `DiscreteUniform`, `DoublyTruncatedPowerLaw`, `EulerMaruyama`, `Exponential`, `FoldedDistribution`, `Gamma`, `GammaPoisson`, `GaussianCopula`, `GaussianCopulaBeta`, `GaussianRandomWalk`, `GaussianStateSpace`, `Geometric`, `Gompertz`, `Gumbel`, `HalfCauchy`, `HalfNormal`, `HurdleGamma`, `HurdleLogNormal`, `HurdleNegativeBinomial2`, `HurdlePoisson`, `ImproperUniform`, `IntervalCensoredDistribution`, `InverseGamma`, `InverseWishart`, `InverseWishartCholesky`, `Kumaraswamy`, `LKJ`, `LKJCholesky`, `Laplace`, `LeftCensoredDistribution`, `Levy`, `LogNormal`, `LogUniform`, `Logistic`, `LowRankMultivariateNormal`, `LowerTruncatedPowerLaw`, `MatrixNormal`, `MixtureGeneral`, `MixtureSameFamily`, `Multinomial`, `MultivariateNormal`, `MultivariateStudentT`, `NegativeBinomial`, `NegativeBinomial2`, `Normal`, `OrderedLogistic`, `Pareto`, `Poisson`, `ProjectedNormal`, `RelaxedBernoulli`, `RightCensoredDistribution`, `SineBivariateVonMises`, `SineSkewed`, `SoftLaplace`, `StudentT`, `TransformedDistribution`, `TruncatedDistribution`, `TruncatedGamma`, `Uniform`, `Unit`, `VonMises`, `Weibull`, `Wishart`, `WishartCholesky`, `ZeroInflatedDistribution`, `ZeroInflatedNegativeBinomial2`, `ZeroInflatedPoisson`, `ZeroSumNormal`, `biject_to`, `constraints`, `flows`, `kl_divergence`, `transforms`.

Distribution objects expose integer tuples `batch_shape` and `event_shape`. The `expand(batch_shape)`, `to_event(reinterpreted_batch_ndims)`, and `mask(mask)` methods return distribution objects; their arguments are an integer shape tuple, an integer event rank, and a boolean scalar or array, respectively.

## `velnora.diagnostics`

The module `velnora.diagnostics` exposes `autocorrelation`, `autocovariance`, `effective_sample_size`, `gelman_rubin`, `hpdi`, `print_summary`, `split_gelman_rubin`, `summary`.

## `velnora.contrib.tfp.mcmc`

The module `velnora.contrib.tfp.mcmc` exposes `HamiltonianMonteCarlo`.

## `velnora.contrib.tfp.distributions`

The module `velnora.contrib.tfp.distributions` exposes `TFPDistribution`.

## `velnora.contrib.stochastic_support.sdvi`

The module `velnora.contrib.stochastic_support.sdvi` exposes `SDVI`.

## `velnora.contrib.stochastic_support.dcc`

The module `velnora.contrib.stochastic_support.dcc` exposes `DCC`.

## `velnora.contrib.nested_sampling`

The module `velnora.contrib.nested_sampling` exposes `NestedSampler`.

## `velnora.contrib.module`

The module `velnora.contrib.module` exposes `eqx_module`, `flax_module`, `nnx_module`, `random_eqx_module`, `random_flax_module`, `random_nnx_module`.

## `velnora.contrib.funsor.infer_util`

The module `velnora.contrib.funsor.infer_util` exposes `log_density`.

## `velnora.contrib.funsor`

The module `velnora.contrib.funsor` exposes `config_enumerate`, `enum`, `infer_discrete`, `infer_util`.

## `velnora.contrib.einstein.stein_kernels`

The module `velnora.contrib.einstein.stein_kernels` exposes `RadialGaussNewtonKernel`.

## `velnora.contrib.einstein`

The module `velnora.contrib.einstein` exposes `ASVGD`, `GraphicalKernel`, `IMQKernel`, `LinearKernel`, `MixtureGuidePredictive`, `MixtureKernel`, `ProbabilityProductKernel`, `RBFKernel`, `RandomFeatureKernel`, `SVGD`, `SteinVI`, `stein_kernels`.

For `SVGD` and `ASVGD`, point locations use `<site>_auto_loc` parameter keys and arrays with a leading particle axis followed by the original model site's shape.

## `velnora.contrib.control_flow`

The module `velnora.contrib.control_flow` exposes `cond`, `scan`.

## `velnora`

The module `velnora` exposes `deterministic`, `diagnostics`, `distributions`, `factor`, `handlers`, `infer`, `module`, `nn`, `optim`, `param`, `plate`, `plate_stack`, `primitives`, `prng_key`, `sample`, `subsample`, `util`, `validation_enabled`.

## `velnora.contrib.hsgp.approximation`

`velnora.contrib.hsgp.approximation` is an importable Python module.

## `velnora.contrib.hsgp.laplacian`

`velnora.contrib.hsgp.laplacian` is an importable Python module.

## `velnora.contrib.hsgp.spectral_densities`

`velnora.contrib.hsgp.spectral_densities` is an importable Python module.

## `velnora.infer.HMCECS.taylor_proxy`

`HMCECS.taylor_proxy(reference_params)` returns a proxy constructor; `reference_params` maps latent-site names to numerical values.
