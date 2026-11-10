# Interface Contract

Import the Python package as `velnora`. Numerical arguments and results use `torch` tensors; callable models and guides are ordinary Python callables. Result mappings use caller-supplied string site names. File-taking calls receive caller-supplied paths.

## `velnora.param`

`param(name[, init_tensor, constraint, event_dim])` returns a differentiable `torch.Tensor` in the parameter domain. `name` is a string, `init_tensor` is a tensor or a zero-argument callable returning a tensor, `constraint` is a constraint object, and `event_dim` is an integer. Missing-parameter lookup raises `KeyError`.

## `velnora.get_param_store`

`get_param_store()` returns the parameter store object.

## `velnora.params.param_store.ParamStoreDict`

The object returned by `get_param_store()` supports `store[name]` tensor lookup, `store[name] = tensor` replacement, and `del store[name]` deletion. `keys()` yields strings; `items()` yields `(name, constrained_tensor)` pairs; `named_parameters()` yields `(name, trainable_tensor)` pairs for optimizer use. `clear()` has no result read. Missing lookup raises `KeyError`.

`save(filename)` and `load(filename)` exchange parameter state through the supplied file path. `scope()` and `scope(state)` are context managers yielding a retained state object that can be passed back as `state`.

## `velnora.clear_param_store`

`clear_param_store()` is the package-level parameter-state clearing call.

## `velnora.sample`

`sample(name, fn[, obs, obs_mask, infer])` returns a sampled or supplied tensor. `name` is a string; `fn` is a distribution object; `obs` is a tensor; `obs_mask` is a boolean tensor. `infer` is a mapping with the string key `enumerate` and string mode values `parallel` or `sequential`. An incompatible observation mask raises `ValueError`.

The `infer` mapping also accepts boolean `is_auxiliary`. Initialization callbacks receive a record containing string `name`.

## `velnora.factor`

`factor(name, log_factor[, has_rsample])` accepts a string name, tensor log factor and optional boolean `has_rsample` declaration. Its result is read through execution probability records.

## `velnora.deterministic`

`deterministic(name, value[, event_dim])` accepts a string name, tensor value and optional integer event dimension; its return is a tensor and its named record exposes `value`.

## `velnora.set_rng_seed`

`set_rng_seed(rng_seed)` accepts an integer seed.

## `velnora.enable_validation`

`enable_validation(is_validate)` accepts a boolean validation selection.

## `velnora.validation_enabled`

`validation_enabled(is_validate)` returns a context manager accepting a boolean validation selection.

## `velnora.plate`

`plate(name, size[, subsample_size, subsample, dim])` is usable as a context manager or iterable. Context entry yields a one-dimensional `torch.long` index tensor; iteration yields member indices. `name` is a string, `size` and `subsample_size` are integers, `subsample` is an integer index tensor, and `dim` is an integer axis. Inconsistent declarations raise `ValueError`.

## `velnora.subsample`

`subsample(data, event_dim)` accepts a tensor and an integer event-dimension count and returns a tensor with selected batch axes and trailing event axes.

## `velnora.markov`

`markov(iterable[, history])` returns an iterable usable in a model loop; `history` is an integer.

## `velnora.poutine.trace`

`trace(fn)` returns a callable execution handler. `get_trace(*args, **kwargs)` returns a `Trace` object, and `trace` on the handler exposes its most recent recorded execution. Duplicate sample names are reported with `RuntimeError`.

## `velnora.poutine.trace_struct.Trace`

`nodes` is a mapping from site-name strings to record mappings. The `_RETURN` record has a `value` field containing the model return. Records expose `type` (including `sample` and `param`), `value`, `is_observed` (boolean), and `fn` (the site distribution). `compute_log_prob()` makes `log_prob` tensor fields available. `log_prob_sum()` returns a scalar joint log-probability tensor.

## `velnora.poutine.condition`

`condition(fn, data)` returns a wrapped callable accepting the original model arguments and returning the original model return form. `data` accepts a name-to-tensor mapping.

## `velnora.poutine.do`

`do(fn, data)` returns a wrapped callable accepting the original model arguments and returning the original model return form. `data` accepts a name-to-tensor mapping.

## `velnora.poutine.uncondition`

`uncondition(fn)` returns a wrapped callable accepting the original model arguments and returning the original model return form.

## `velnora.poutine.replay`

`replay(fn, trace)` returns a wrapped callable accepting the original model arguments and returning the original model return form. `trace` accepts an execution trace. The form omitting `fn` supplies a context manager or callable decorator.

## `velnora.poutine.block`

`block(fn[, hide, expose])` returns a wrapped callable accepting the original model arguments and returning the original model return form. Each supplied selection argument accepts a list of string site names.

## `velnora.poutine.substitute`

`substitute(fn, data)` returns a wrapped callable accepting the original model arguments and returning the original model return form. `data` accepts a name-to-tensor mapping.

## `velnora.poutine.lift`

`lift(fn, prior)` returns a wrapped callable accepting the original model arguments and returning the original model return form. `prior` accepts a name-to-distribution mapping.

## `velnora.poutine.scale`

`scale(fn, scale)` returns a wrapped callable accepting the original model arguments and returning the original model return form. `scale` accepts a numeric scalar or tensor. The form omitting `fn` supplies a context manager or callable decorator. Rejected probability weights raise `ValueError`.

## `velnora.poutine.mask`

`mask(fn, mask)` returns a wrapped callable accepting the original model arguments and returning the original model return form. `mask` accepts a boolean scalar or tensor. The form omitting `fn` supplies a context manager or callable decorator.

## `velnora.poutine.seed`

`seed(fn, rng_seed)` returns a wrapped callable accepting the original model arguments and returning the original model return form. `rng_seed` accepts an integer seed. The form omitting `fn` supplies a context manager or callable decorator.

## `velnora.poutine.reparam`

`reparam(fn, config)` returns a wrapped callable accepting the original model arguments and returning the original model return form. `config` accepts a name-to-reparameterizer mapping.

## `velnora.ops.indexing.Vindex`

`Vindex(tensor)[indices]` returns a tensor. Index expressions accept integers, integer tensors, full slices `:`, and a leading ellipsis `...`. The result carries broadcast index batch axes followed by the unselected event axes.

## `velnora.infer.inspect.get_dependencies`

`get_dependencies(model[, model_args, model_kwargs])` accepts a callable, positional-argument tuple and keyword-argument mapping. It returns a dictionary with `prior_dependencies` and `posterior_dependencies`. Each field is a mapping `{site_name: {neighbor_name: set_of_population_names}}` using string names.

## `velnora.distributions`

Distribution objects use `batch_shape` and `event_shape` as tuples of axis sizes. `sample(sample_shape)` and differentiable `rsample(sample_shape)` return tensors with axes `sample_shape + batch_shape + event_shape`. `log_prob(value)` returns a tensor with the event axes reduced. `expand(batch_shape)`, `to_event(reinterpreted_batch_ndims)` and `mask(mask)` return distribution objects. `mean` and `variance` are tensor-valued moments; `covariance_matrix` is a tensor of matrix-valued covariance. Distribution objects returned as conditional results can expose `probs`, `loc`, `scale`, `rate`, `df`, `concentration` and `base_dist` with their named parameter meanings.

## `velnora.distributions.Bernoulli`

`Bernoulli([probs, logits])` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Binomial`

`Binomial(total_count[, probs])` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Categorical`

`Categorical([probs, validate_args])` constructs a distribution. Distribution parameters accept numerical scalars or tensors. `validate_args` is boolean.

Input rejection from construction or `log_prob` is reported as `ValueError`.

## `velnora.distributions.Multinomial`

`Multinomial(total_count, probs)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Geometric`

`Geometric(probs)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Poisson`

`Poisson(rate[, validate_args])` constructs a distribution. Distribution parameters accept numerical scalars or tensors. `validate_args` is boolean.

Input rejection from construction or `log_prob` is reported as `ValueError`.

## `velnora.distributions.NegativeBinomial`

`NegativeBinomial(total_count, probs)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Beta`

`Beta(concentration1, concentration0[, validate_args])` constructs a distribution. Distribution parameters accept numerical scalars or tensors. `validate_args` is boolean.

Input rejection from construction or `log_prob` is reported as `ValueError`.

## `velnora.distributions.ContinuousBernoulli`

`ContinuousBernoulli(probs)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Cauchy`

`Cauchy(loc, scale)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Chi2`

`Chi2(df)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Exponential`

`Exponential(rate)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.FisherSnedecor`

`FisherSnedecor(df1, df2)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Gamma`

`Gamma(concentration, rate)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.InverseGamma`

`InverseGamma(concentration, rate)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Gumbel`

`Gumbel(loc, scale)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.HalfCauchy`

`HalfCauchy(scale)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.HalfNormal`

`HalfNormal(scale)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Kumaraswamy`

`Kumaraswamy(concentration1, concentration0)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Laplace`

`Laplace(loc, scale)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Logistic`

`Logistic(loc, scale)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Normal`

`Normal(loc, scale[, validate_args])` constructs a distribution. Distribution parameters accept numerical scalars or tensors. `validate_args` is boolean.

Input rejection from construction or `log_prob` is reported as `ValueError`.

## `velnora.distributions.LogNormal`

`LogNormal(loc, scale)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Pareto`

`Pareto(scale, alpha)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.StudentT`

`StudentT(df[, loc, scale])` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Uniform`

`Uniform(low, high)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.VonMises`

`VonMises(loc, concentration)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.Weibull`

`Weibull(scale, concentration)` constructs a distribution. Distribution parameters accept numerical scalars or tensors.

## `velnora.distributions.MultivariateNormal`

`MultivariateNormal(loc[, covariance_matrix, scale_tril, validate_args])` constructs a distribution. Numeric parameters are scalars or tensors.

Input rejection from construction or `log_prob` is reported as `ValueError`.

## `velnora.distributions.LowRankMultivariateNormal`

`LowRankMultivariateNormal(loc, cov_factor, cov_diag)` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.MultivariateStudentT`

`MultivariateStudentT(df[, loc, scale_tril])` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.Dirichlet`

`Dirichlet(concentration)` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.LogisticNormal`

`LogisticNormal(loc, scale)` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.Wishart`

`Wishart(df, covariance_matrix)` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.LKJ`

`LKJ(dim, concentration)` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.Delta`

`Delta(v[, event_dim])` constructs a distribution. Numeric parameters are scalars or tensors. `event_dim` is an integer.

## `velnora.distributions.BetaBinomial`

`BetaBinomial(concentration1, concentration0[, total_count])` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.DirichletMultinomial`

`DirichletMultinomial(concentration[, total_count])` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.GammaPoisson`

`GammaPoisson(concentration, rate)` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.ZeroInflatedPoisson`

`ZeroInflatedPoisson(rate[, gate])` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.ZeroInflatedNegativeBinomial`

`ZeroInflatedNegativeBinomial(total_count[, probs, gate])` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.Empirical`

`Empirical(samples, log_weights)` constructs a distribution. Numeric parameters are scalars or tensors.

Unsupported moment access raises `ValueError`.

## `velnora.distributions.MixtureOfDiagNormals`

`MixtureOfDiagNormals(locs, coord_scale, component_logits)` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.MixtureOfDiagNormalsSharedCovariance`

`MixtureOfDiagNormalsSharedCovariance(locs, coord_scale, component_logits)` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.MaskedMixture`

`MaskedMixture(mask, component0, component1)` constructs a distribution. `mask` is boolean-valued and the two components are distribution objects.

## `velnora.distributions.NanMaskedNormal`

`NanMaskedNormal(loc, scale)` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.NanMaskedMultivariateNormal`

`NanMaskedMultivariateNormal(loc[, covariance_matrix])` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.OrderedLogistic`

`OrderedLogistic(predictor, cutpoints)` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.ProjectedNormal`

`ProjectedNormal(concentration)` constructs a distribution. Numeric parameters are scalars or tensors.

Unsupported density evaluation raises `NotImplementedError`.

## `velnora.distributions.Stable`

`Stable(stability, skew[, scale, loc])` constructs a distribution. Numeric parameters are scalars or tensors.

## `velnora.distributions.TorchDistribution`

`TorchDistribution` is a subclassable distribution base. Caller-defined subclasses can provide `sample`, `rsample`, `log_prob`, `batch_shape` and `event_shape` using the tensor distribution call forms.

A subclass constructor can call the base with `(batch_shape, event_shape, validate_args=...)`. A caller-defined implicit distribution declares `arg_constraints`, `support` and boolean `has_rsample` and can supply `expand(batch_shape)`.

## `velnora.distributions.TransformedDistribution`

`TransformedDistribution(base_distribution, transforms)` accepts a base distribution and an ordered list of transform objects and returns a distribution. Its `transforms` attribute is the transform list. `sample(sample_shape)`, `rsample(sample_shape)` and `log_prob(value)` use tensor distribution result forms.

## `velnora.distributions.ConditionalTransformedDistribution`

`ConditionalTransformedDistribution(base_dist, transforms)` accepts a base distribution and transform list. `condition(context)` accepts a tensor and returns a transformed distribution whose `transforms` list exposes the conditioned transforms.

## `velnora.distributions.constraints`

Constraint objects are exposed as `real`, `positive`, `simplex`, `positive_definite`, `lower_cholesky`, `ordered_vector` and `corr_matrix`; `interval(lower_bound, upper_bound)` constructs a bounded constraint. `check(value)` returns a boolean tensor over batch members.

## `velnora.nn.VelnoraModule`

`VelnoraModule` is subclassable, and `VelnoraModule[ModuleClass]` supplies a class constructed with the wrapped neural component constructor arguments. Instances support caller-defined `forward` and ordinary tensor attributes, nested named components, `parameters()`, `named_parameters()`, `state_dict()` and `load_state_dict(state)`. Named parameter and random-attribute records use dot-separated attribute paths. For an unconstrained neural parameter, querying `velnora.param` by its recorded path returns the same tensor object exposed by the component.

## `velnora.nn.VelnoraParam`

`VelnoraParam(init_value, constraint)` declares a tensor-valued module attribute; `init_value` is a tensor and `constraint` is a constraint object.

## `velnora.nn.VelnoraSample`

`VelnoraSample(prior)` declares a random module attribute. `prior` is a distribution or a callable receiving the module and returning a distribution.

## `velnora.nn.DenseNN`

`DenseNN(input_dim, hidden_dims[, param_dims, nonlinearity])` returns a trainable neural module. Input and context dimensions and parameter dimensions are integers; `hidden_dims` and `param_dims` are sequences of integers; `nonlinearity` is a neural module. Invocation is `forward(x)` with a tensor. The result for multiple parameter groups is a tuple of tensors, each with shape `batch_shape + (parameter_dimension,)`. `parameters()` yields trainable tensors.

## `velnora.nn.ConditionalDenseNN`

`ConditionalDenseNN(input_dim, context_dim, hidden_dims[, param_dims, nonlinearity])` returns a trainable neural module. Input and context dimensions and parameter dimensions are integers; `hidden_dims` and `param_dims` are sequences of integers; `nonlinearity` is a neural module. Invocation is `forward(x, context)` with tensors; `context` can be supplied by keyword. The result for multiple parameter groups is a tuple of tensors, each with shape `batch_shape + (parameter_dimension,)`. `parameters()` yields trainable tensors.

## `velnora.nn.AutoRegressiveNN`

`AutoRegressiveNN(input_dim, hidden_dims[, param_dims, permutation, nonlinearity])` returns a trainable neural module. Input and context dimensions and parameter dimensions are integers; `hidden_dims` and `param_dims` are sequences of integers; `nonlinearity` is a neural module. `permutation` is an integer tensor. Invocation is `forward(x)` with a tensor. For multiple parameter groups, the result is a tuple of tensors with shapes `batch_shape + (parameter_dimension, input_dim)`. A single unit parameter group returns a tensor of shape `batch_shape + (input_dim,)`. `parameters()` yields trainable tensors.

## `velnora.nn.ConditionalAutoRegressiveNN`

`ConditionalAutoRegressiveNN(input_dim, context_dim, hidden_dims[, param_dims, permutation, nonlinearity])` returns a trainable neural module. Input and context dimensions and parameter dimensions are integers; `hidden_dims` and `param_dims` are sequences of integers; `nonlinearity` is a neural module. `permutation` is an integer tensor. Invocation is `forward(x, context)` with tensors; `context` can be supplied by keyword. For multiple parameter groups, the result is a tuple of tensors with shapes `batch_shape + (parameter_dimension, input_dim)`. A single unit parameter group returns a tensor of shape `batch_shape + (input_dim,)`. `parameters()` yields trainable tensors.

## `velnora.contrib.bnn.HiddenLayer`

`HiddenLayer(X, A_mean, A_scale[, non_linearity, KL_factor, include_hidden_bias])` accepts input and weight tensors, an activation callable, a numeric factor and a boolean bias-column selection. `rsample(sample_shape)` accepts `torch.Size` and returns a tensor with shape `sample_shape + (input_rows, output_width)`, where the optional bias activation is the last column. `log_prob(value)` returns a scalar divergence-contribution tensor.

## `velnora.distributions.transforms.affine_autoregressive`

`affine_autoregressive(input_dim)` returns a trainable transform. `input_dim` is an integer. The returned module supports `double()`, `parameters()`, tensor invocation, `inv(value)` and `log_abs_det_jacobian(x, y)`. Invocation and inverse return tensors with the input event width; volume results are scalar or per-coordinate tensors.

## `velnora.distributions.transforms.affine_coupling`

`affine_coupling(input_dim)` returns a trainable transform. `input_dim` is an integer. The returned module supports `double()`, `parameters()`, tensor invocation, `inv(value)` and `log_abs_det_jacobian(x, y)`. Invocation and inverse return tensors with the input event width; volume results are scalar or per-coordinate tensors.

## `velnora.distributions.transforms.batchnorm`

`batchnorm(input_dim)` returns a trainable transform. `input_dim` is an integer. The returned module supports `double()`, `parameters()`, tensor invocation, `inv(value)` and `log_abs_det_jacobian(x, y)`. Invocation and inverse return tensors with the input event width; volume results are scalar or per-coordinate tensors. `eval()` selects evaluation mode.

## `velnora.distributions.transforms.block_autoregressive`

`block_autoregressive(input_dim[, hidden_factors, activation])` returns a trainable transform. `input_dim` is an integer. The returned module supports `double()`, `parameters()`, tensor invocation, `inv(value)` and `log_abs_det_jacobian(x, y)`. Invocation and inverse return tensors with the input event width; volume results are scalar or per-coordinate tensors.

`hidden_factors` is a list of positive integers and `activation` is a string selection, including `tanh`.

## `velnora.distributions.transforms.neural_autoregressive`

`neural_autoregressive(input_dim[, width, activation])` returns a trainable transform. `input_dim` is an integer. The returned module supports `double()`, `parameters()`, tensor invocation, `inv(value)` and `log_abs_det_jacobian(x, y)`. Invocation and inverse return tensors with the input event width; volume results are scalar or per-coordinate tensors.

`width` is an integer and `activation` is spelled `sigmoid` or `tanh`.

## `velnora.distributions.transforms.planar`

`planar(input_dim)` returns a trainable transform. `input_dim` is an integer. The returned module supports `double()`, `parameters()`, tensor invocation, `inv(value)` and `log_abs_det_jacobian(x, y)`. Invocation and inverse return tensors with the input event width; volume results are scalar or per-coordinate tensors.

## `velnora.distributions.transforms.polynomial`

`polynomial(input_dim)` returns a trainable transform. `input_dim` is an integer. The returned module supports `double()`, `parameters()`, tensor invocation, `inv(value)` and `log_abs_det_jacobian(x, y)`. Invocation and inverse return tensors with the input event width; volume results are scalar or per-coordinate tensors.

## `velnora.distributions.transforms.radial`

`radial(input_dim)` returns a trainable transform. `input_dim` is an integer. The returned module supports `double()`, `parameters()`, tensor invocation, `inv(value)` and `log_abs_det_jacobian(x, y)`. Invocation and inverse return tensors with the input event width; volume results are scalar or per-coordinate tensors.

## `velnora.distributions.transforms.spline`

`spline(input_dim[, count_bins, bound, order])` returns a trainable transform. `input_dim` is an integer. The returned module supports `double()`, `parameters()`, tensor invocation, `inv(value)` and `log_abs_det_jacobian(x, y)`. Invocation and inverse return tensors with the input event width; volume results are scalar or per-coordinate tensors.

`count_bins` is an integer, `bound` is numeric and `order` is a string selection. Rejected bounds raise `AssertionError`; rejected orders raise `ValueError`.

Spline-order selections are spelled `linear` and `quadratic`.

## `velnora.distributions.transforms.spline_autoregressive`

`spline_autoregressive(input_dim[, count_bins, bound, order])` returns a trainable transform. `input_dim` is an integer. The returned module supports `double()`, `parameters()`, tensor invocation, `inv(value)` and `log_abs_det_jacobian(x, y)`. Invocation and inverse return tensors with the input event width; volume results are scalar or per-coordinate tensors.

`count_bins` is an integer, `bound` is numeric, and `order` selections are spelled `linear` and `quadratic`.

## `velnora.distributions.transforms.spline_coupling`

`spline_coupling(input_dim[, count_bins, bound])` returns a trainable transform. `input_dim` is an integer. The returned module supports `double()`, `parameters()`, tensor invocation, `inv(value)` and `log_abs_det_jacobian(x, y)`. Invocation and inverse return tensors with the input event width; volume results are scalar or per-coordinate tensors.

`count_bins` is an integer and `bound` is numeric.

## `velnora.distributions.transforms.sylvester`

`sylvester(input_dim)` returns a trainable transform. `input_dim` is an integer. The returned module supports `double()`, `parameters()`, tensor invocation, `inv(value)` and `log_abs_det_jacobian(x, y)`. Invocation and inverse return tensors with the input event width; volume results are scalar or per-coordinate tensors.

## `velnora.distributions.transforms.conditional_affine_autoregressive`

`conditional_affine_autoregressive(input_dim, context_dim)` accepts integer dimensions and returns a trainable module supporting `double()`. `condition(context)` takes a tensor and returns a tensor transform with `inv(value)` and `log_abs_det_jacobian(x, y)`. Generated tensors retain sample and context batch axes before the event axis. `parameters()` returns an iterable of trainable tensors.

## `velnora.distributions.transforms.conditional_affine_coupling`

`conditional_affine_coupling(input_dim, context_dim)` accepts integer dimensions and returns a trainable module supporting `double()`. `condition(context)` takes a tensor and returns a tensor transform with `inv(value)` and `log_abs_det_jacobian(x, y)`. Generated tensors retain sample and context batch axes before the event axis. `parameters()` returns an iterable of trainable tensors.

## `velnora.distributions.transforms.conditional_neural_autoregressive`

`conditional_neural_autoregressive(input_dim, context_dim[, width, activation])` accepts integer dimensions and returns a trainable module supporting `double()`. `condition(context)` takes a tensor and returns a tensor transform with `inv(value)` and `log_abs_det_jacobian(x, y)`. Generated tensors retain sample and context batch axes before the event axis.

`width` is an integer and `activation` is spelled `sigmoid` or `tanh`. `parameters()` returns an iterable of trainable tensors.

## `velnora.distributions.transforms.conditional_planar`

`conditional_planar(input_dim, context_dim)` accepts integer dimensions and returns a trainable module supporting `double()`. `condition(context)` takes a tensor and returns a tensor transform with `inv(value)` and `log_abs_det_jacobian(x, y)`. Generated tensors retain sample and context batch axes before the event axis. `parameters()` returns an iterable of trainable tensors.

## `velnora.distributions.transforms.conditional_radial`

`conditional_radial(input_dim, context_dim)` accepts integer dimensions and returns a trainable module supporting `double()`. `condition(context)` takes a tensor and returns a tensor transform with `inv(value)` and `log_abs_det_jacobian(x, y)`. Generated tensors retain sample and context batch axes before the event axis. `parameters()` returns an iterable of trainable tensors.

## `velnora.distributions.transforms.conditional_spline`

`conditional_spline(input_dim, context_dim[, count_bins, bound, order])` accepts integer dimensions and returns a trainable module supporting `double()`. `condition(context)` takes a tensor and returns a tensor transform with `inv(value)` and `log_abs_det_jacobian(x, y)`. Generated tensors retain sample and context batch axes before the event axis.

`count_bins` is an integer, `bound` is numeric, and `order` selections are spelled `linear` and `quadratic`. `parameters()` returns an iterable of trainable tensors.

## `velnora.distributions.transforms.conditional_spline_autoregressive`

`conditional_spline_autoregressive(input_dim, context_dim[, count_bins, bound, order])` accepts integer dimensions and returns a trainable module supporting `double()`. `condition(context)` takes a tensor and returns a tensor transform with `inv(value)` and `log_abs_det_jacobian(x, y)`. Generated tensors retain sample and context batch axes before the event axis.

`count_bins` is an integer, `bound` is numeric, and `order` selections are spelled `linear` and `quadratic`. `parameters()` returns an iterable of trainable tensors.

## `velnora.distributions.transforms.AffineTransform`

`AffineTransform(loc, scale)` constructs a transform with tensor invocation and `inv(value)`. Numeric parameters, when supplied, are scalars or tensors.

## `velnora.distributions.transforms.ExpTransform`

`ExpTransform()` constructs a transform with tensor invocation and `inv(value)`.

## `velnora.distributions.transforms.OrderedTransform`

`OrderedTransform()` constructs a transform with tensor invocation and `inv(value)`.

## `velnora.distributions.transforms.TanhTransform`

`TanhTransform()` constructs a transform with tensor invocation and `inv(value)`.

## `velnora.distributions.transforms.ComposeTransform`

`ComposeTransform(parts)` constructs a transform with tensor invocation and `inv(value)`. `parts` is an ordered sequence of transforms.

## `velnora.distributions.transforms.transform_to`

`transform_to(constraint)` returns a transform with tensor invocation and `inv(value)`; matrix constraints use matrix event tensors.

## `velnora.infer.reparam.LocScaleReparam`

`LocScaleReparam([centered])` constructs a reparameterizer accepted in `config` by `reparam`. Its externally addressable auxiliary sites use the original site name followed by `_decentered`.

## `velnora.infer.reparam.TransformReparam`

`TransformReparam()` constructs a reparameterizer accepted in `config` by `reparam`. Its externally addressable auxiliary sites use the original site name followed by `_base`.

## `velnora.infer.reparam.StudentTReparam`

`StudentTReparam()` constructs a reparameterizer accepted in `config` by `reparam`. Its externally addressable auxiliary sites use the original site name followed by `_gamma`.

## `velnora.infer.reparam.LatentStableReparam`

`LatentStableReparam()` constructs a reparameterizer accepted in `config` by `reparam`. Its externally addressable auxiliary sites use the original site name followed by `_uniform`, `_exponential`.

## `velnora.infer.reparam.ProjectedNormalReparam`

`ProjectedNormalReparam()` constructs a reparameterizer accepted in `config` by `reparam`. Its externally addressable auxiliary sites use the original site name followed by `_normal`.

## `velnora.infer.reparam.DiscreteCosineReparam`

`DiscreteCosineReparam(dim)` constructs a reparameterizer accepted in `config` by `reparam`. Its externally addressable auxiliary sites use the original site name followed by `_dct`.

## `velnora.infer.reparam.HaarReparam`

`HaarReparam(dim[, flip])` constructs a reparameterizer accepted in `config` by `reparam`. Its externally addressable auxiliary sites use the original site name followed by `_haar`. `dim` is an integer axis and `flip` is boolean.

## `velnora.infer.reparam.SplitReparam`

`SplitReparam(sections, dim)` constructs a reparameterizer accepted in `config` by `reparam`. Its externally addressable auxiliary sites use the original site name followed by `_split_`. The `_split_` suffix is followed by the zero-based part index; `sections` is a list of integer part sizes and `dim` is an integer axis. A rejected observed partition raises `RuntimeError`.

## `velnora.optim.VelnoraOptim`

`VelnoraOptim(optim_constructor, optim_args[, clip_args])` returns an optimizer wrapper. `optim_constructor` is an optimizer class; `optim_args` is a settings mapping or callable receiving a parameter name and returning such a mapping; `clip_args` is a clipping mapping or a callable `(module_name, param_name)` returning a clipping mapping. `__call__(params)` accepts an iterable of trainable tensors. Settings read by supplied optimizers include `lr` and `momentum`; clipping mappings use `clip_norm` and `clip_value`.

`get_state()` returns an opaque name-keyed optimizer-state mapping; `set_state(state_dict)` accepts it. `save(filename)` and `load(filename)` exchange this state through a caller-supplied file path.

## `velnora.optim.VelnoraLRScheduler`

`VelnoraLRScheduler(scheduler_constructor, optim_args)` accepts a scheduler class and settings mapping. The mapping contains `optimizer`, `optim_args`, and scheduler-specific settings including `step_size`, `gamma`, `mode`, `factor` and `patience`. `__call__(params)` receives trainable tensors. `step()` or `step(metric)` advances the schedule, with a scalar metric for a monitored schedule.

## `velnora.optim.Adam`

`Adam(optim_args)` accepts an optimizer settings mapping, including `lr`, and returns a callable optimizer wrapper accepting trainable tensors.

## `velnora.optim.SGD`

`SGD(optim_args)` accepts an optimizer settings mapping, including `lr`, and returns a callable optimizer wrapper accepting trainable tensors.

## `velnora.optim.multi.MixedMultiOptimizer`

`MixedMultiOptimizer(parts)` accepts a sequence of `(names, optimizer)` pairs, with string-name lists and optimizer wrappers. `step(loss, params)` accepts a scalar differentiable tensor and a name-to-trainable-tensor mapping. Rejected overlapping assignments raise `ValueError`.

## `velnora.optim.multi.Newton`

`Newton()` constructs an optimizer accepted in `MixedMultiOptimizer` groups.

## `velnora.ops.newton.newton_step`

`newton_step(loss, x[, trust_radius])` accepts a scalar differentiable tensor, a parameter tensor of shape `batch_shape + (dimension,)` and an optional numeric radius. It returns `(updated, covariance)` tensors with shapes `batch_shape + (dimension,)` and `batch_shape + (dimension, dimension)`.

## `velnora.infer.SVI`

`SVI(model, guide, optim, loss)` accepts callable model and guide, an optimizer, and an objective object or callable. `step(*args, **kwargs)` and `evaluate_loss(*args, **kwargs)` pass arguments to the model and guide and return numeric scalar losses.

## `velnora.infer.Trace_ELBO`

`Trace_ELBO([num_particles, vectorize_particles, max_plate_nesting])` constructs an objective. The particle count and nesting depth are integers and vectorization selection is boolean. `loss(model, guide, *args, **kwargs)` returns a numeric scalar; `differentiable_loss(model, guide, *args, **kwargs)` returns a scalar tensor supporting autograd.

Incompatible or incomplete latent specifications raise `ValueError`.

## `velnora.infer.TraceMeanField_ELBO`

`TraceMeanField_ELBO([num_particles, vectorize_particles, max_plate_nesting])` constructs an objective. The particle count and nesting depth are integers and vectorization selection is boolean. `loss(model, guide, *args, **kwargs)` returns a numeric scalar; `differentiable_loss(model, guide, *args, **kwargs)` returns a scalar tensor supporting autograd.

## `velnora.infer.TraceEnum_ELBO`

`TraceEnum_ELBO([num_particles, vectorize_particles, max_plate_nesting])` constructs an objective. The particle count and nesting depth are integers and vectorization selection is boolean. `loss(model, guide, *args, **kwargs)` returns a numeric scalar; `differentiable_loss(model, guide, *args, **kwargs)` returns a scalar tensor supporting autograd.

`compute_marginals(model, guide)` returns a mapping from latent-site strings to distribution objects whose `probs` tensors have shape `population_shape + (support_size,)`. Unsupported model enumeration raises `NotImplementedError`; rejected probability weighting raises `ValueError`.

## `velnora.infer.config_enumerate`

`config_enumerate(guide)` returns a callable, and supports use as a function decorator on a probabilistic program.

## `velnora.infer.infer_discrete`

`infer_discrete(fn, first_available_dim[, temperature])` returns a callable with the original model arguments and return structure, with state tensors at its returned sites. The dimension is an integer and temperature is numeric. Rejected temperature raises `ValueError`; an invalid enumeration dimension raises `AssertionError`.

## `velnora.infer.EnergyDistance`

`EnergyDistance([beta, prior_scale, num_particles, max_plate_nesting])` accepts numeric exponent and prior weight and integer draw count and nesting depth. Calling the object as `(model, guide, *args, **kwargs)` returns a scalar differentiable objective tensor. Rejected objective configurations or model/guide inputs raise `ValueError`.

## `velnora.infer.autoguide.AutoDelta`

`AutoDelta(model[, init_loc_fn])` constructs a callable guide for a model. Calling it with the model arguments returns a mapping `{site_name: sample_tensor}` with string site keys and original-domain tensor values. `median(*args, **kwargs)` returns a site-to-tensor mapping. `init_loc_fn` can be a callable receiving a site record and returning an initial tensor. Unsupported latent domains raise `ValueError`.

## `velnora.infer.autoguide.AutoNormal`

`AutoNormal(model)` constructs a callable guide for a model. Calling it with the model arguments returns a mapping `{site_name: sample_tensor}` with string site keys and original-domain tensor values. `median(*args, **kwargs)` returns a site-to-tensor mapping. `quantiles(quantiles, *args, **kwargs)` accepts a sequence of probabilities and returns site-to-tensor mappings with a leading requested-quantile axis. `init_loc_fn` can be a callable receiving a site record and returning an initial tensor. Unsupported latent domains raise `ValueError`. `locs` and `scales` expose per-site tensor attributes.

The constructor also accepts `init_loc_fn` as an initialization callable.

## `velnora.infer.autoguide.AutoDiagonalNormal`

`AutoDiagonalNormal(model)` constructs a callable guide for a model. Calling it with the model arguments returns a mapping `{site_name: sample_tensor}` with string site keys and original-domain tensor values. `median(*args, **kwargs)` returns a site-to-tensor mapping. `quantiles(quantiles, *args, **kwargs)` accepts a sequence of probabilities and returns site-to-tensor mappings with a leading requested-quantile axis. `init_loc_fn` can be a callable receiving a site record and returning an initial tensor. Unsupported latent domains raise `ValueError`. `get_posterior(*args, **kwargs)` returns a distribution with `rsample` and `log_prob`; the normal posterior results also expose tensor `mean` and `variance`.

The constructor also accepts `init_loc_fn` as an initialization callable.

## `velnora.infer.autoguide.AutoMultivariateNormal`

`AutoMultivariateNormal(model)` constructs a callable guide for a model. Calling it with the model arguments returns a mapping `{site_name: sample_tensor}` with string site keys and original-domain tensor values. `median(*args, **kwargs)` returns a site-to-tensor mapping. `quantiles(quantiles, *args, **kwargs)` accepts a sequence of probabilities and returns site-to-tensor mappings with a leading requested-quantile axis. `init_loc_fn` can be a callable receiving a site record and returning an initial tensor. Unsupported latent domains raise `ValueError`. `get_posterior(*args, **kwargs)` returns a distribution with `rsample` and `log_prob`; the normal posterior results also expose tensor `mean` and `variance`.

The constructor also accepts `init_loc_fn` as an initialization callable.

The posterior distribution exposes `covariance_matrix` as a tensor.

## `velnora.infer.autoguide.AutoLowRankMultivariateNormal`

`AutoLowRankMultivariateNormal(model)` constructs a callable guide for a model. Calling it with the model arguments returns a mapping `{site_name: sample_tensor}` with string site keys and original-domain tensor values. `median(*args, **kwargs)` returns a site-to-tensor mapping. `quantiles(quantiles, *args, **kwargs)` accepts a sequence of probabilities and returns site-to-tensor mappings with a leading requested-quantile axis. `init_loc_fn` can be a callable receiving a site record and returning an initial tensor. Unsupported latent domains raise `ValueError`. `get_posterior(*args, **kwargs)` returns a distribution with `rsample` and `log_prob`; the normal posterior results also expose tensor `mean` and `variance`.

The constructor also accepts `init_loc_fn` as an initialization callable.

The posterior distribution exposes `covariance_matrix` as a tensor.

## `velnora.infer.autoguide.AutoNormalizingFlow`

`AutoNormalizingFlow(model, init_transform_fn)` constructs a callable guide for a model. Calling it with the model arguments returns a mapping `{site_name: sample_tensor}` with string site keys and original-domain tensor values. `get_posterior(*args, **kwargs)` returns a distribution with `rsample` and `log_prob`. `init_transform_fn` is a callable receiving the latent dimension and returning a transform.

## `velnora.infer.autoguide.AutoIAFNormal`

`AutoIAFNormal(model)` constructs a callable guide for a model. Calling it with the model arguments returns a mapping `{site_name: sample_tensor}` with string site keys and original-domain tensor values. `get_posterior(*args, **kwargs)` returns a distribution with `rsample` and `log_prob`.

## `velnora.infer.autoguide.AutoGuideList`

`AutoGuideList(model)` constructs a callable guide for a model. Calling it with the model arguments returns a mapping `{site_name: sample_tensor}` with string site keys and original-domain tensor values. `append(part)` accepts a guide callable or guide object.

## `velnora.infer.autoguide.AutoStructured`

`AutoStructured(model[, conditionals, dependencies, init_loc_fn, init_scale])` constructs a callable guide for a model. Calling it with the model arguments returns a mapping `{site_name: sample_tensor}` with string site keys and original-domain tensor values. `conditionals` is a site-name-to-string-or-callable mapping; `dependencies` is a nested site-name mapping with string-or-callable entries; `init_scale` is numeric.

String conditional selections are spelled `delta`, `normal` and `mvn`.

## `velnora.infer.autoguide.AutoGaussian`

`AutoGaussian(model[, backend])` constructs a callable guide for a model. Calling it with the model arguments returns a mapping `{site_name: sample_tensor}` with string site keys and original-domain tensor values. `backend` is a string selection.

The dense backend selection is spelled `dense`.

## `velnora.infer.autoguide.AutoDiscreteParallel`

`AutoDiscreteParallel(model)` constructs a callable guide for a model. Calling it with the model arguments returns a mapping `{site_name: sample_tensor}` with string site keys and original-domain tensor values. Learned site probability tensors are exposed as attributes named by appending `_probs` to the site name. Unsupported configurations raise `NotImplementedError`.

The per-site probability attribute has the form `<site>_probs`.

## `velnora.infer.autoguide.AutoLaplaceApproximation`

`AutoLaplaceApproximation(model[, init_loc_fn])` constructs a callable guide for a model. Calling it with the model arguments returns a mapping `{site_name: sample_tensor}` with string site keys and original-domain tensor values. `laplace_approximation()` returns a guide with `get_posterior()`, whose distribution exposes `mean`, `covariance_matrix` and `log_prob`.

## `velnora.infer.autoguide.init_to_value`

`init_to_value(values=mapping)` returns an initialization callable; `values` maps string site names to tensor initial values.

## `velnora.infer.mcmc.HMC`

`HMC([model, potential_fn, step_size, num_steps])` constructs a kernel accepted by sampling drivers. `model` is a callable. A supplied `potential_fn` is a callable from a name-to-tensor mapping to a scalar negative-log-density tensor. Kernel `initial_params` is a name-to-tensor mapping readable by a sampling hook.

## `velnora.infer.mcmc.NUTS`

`NUTS([model, potential_fn, max_plate_nesting])` constructs a kernel accepted by sampling drivers. `model` is a callable. A supplied `potential_fn` is a callable from a name-to-tensor mapping to a scalar negative-log-density tensor. Kernel `initial_params` is a name-to-tensor mapping readable by a sampling hook.

## `velnora.infer.mcmc.RandomWalkKernel`

`RandomWalkKernel(model[, init_step_size])` constructs a kernel accepted by sampling drivers. `model` is a callable. Kernel `initial_params` is a name-to-tensor mapping readable by a sampling hook.

## `velnora.infer.mcmc.MCMC`

`MCMC(kernel, num_samples[, warmup_steps, initial_params, num_chains, hook_fn, disable_progbar, save_params])` constructs a sampling driver. Counts are integers, `disable_progbar` is boolean, `save_params` is a list of site-name strings and `initial_params` maps strings to tensors. `run(*args, **kwargs)` passes arguments to the model. `hook_fn(kernel, samples, stage, index)` receives a name-to-tensor mapping in sampling coordinates and an integer index. For scalar sites supported on the open unit interval, callback values are log odds. Stage labels are `Warmup` or `Sample` for worker callbacks, or `Warmup [<chain>]` and `Sample [<chain>]` for sequential chains, with a zero-based chain number. Indices are zero-based within the stage. `get_samples([group_by_chain])` returns a string-to-tensor mapping; grouped tensors have axes `(chain, draw, ...)` and combined tensors have axes `(combined_draw, ...)`. Initialization failure raises `ValueError`.

## `velnora.infer.mcmc.StreamingMCMC`

`StreamingMCMC(kernel, num_samples[, warmup_steps, initial_params, statistics, num_chains, hook_fn, disable_progbar, save_params])` constructs a sampling driver. Counts are integers, `disable_progbar` is boolean, `save_params` is a list of site-name strings and `initial_params` maps strings to tensors. `run(*args, **kwargs)` passes arguments to the model. `hook_fn(kernel, samples, stage, index)` receives a name-to-tensor mapping in sampling coordinates and an integer index. Stage labels are `Warmup [<chain>]` and `Sample [<chain>]`, with a zero-based chain number. Indices are zero-based within the stage. `get_statistics([group_by_chain])` returns a mapping keyed by `(chain, site_name)` when grouped and by `site_name` when combined. Built-in summaries expose `count` as an integer and `mean` and `variance` as tensors of the sampled event shape. `statistics` accepts a `StatsOfDict` accumulator. A caller accumulator provides `update(sample)`, `merge(other)` returning a merged accumulator, and `get()` returning a summary mapping.

With `StatsOfDict(default=StackStats)`, each summary exposes integer `count` and a `samples` tensor with a leading draw axis. A caller-provided accumulator returns its own summary mapping, such as tensor `covariance`.

## `velnora.ops.streaming.StatsOfDict`

`StatsOfDict(default=constructor)` accepts a zero-argument accumulator constructor and supplies the `statistics` object for `StreamingMCMC`. Values sent to the selected accumulators are sample tensors; their `get()` result supplies the per-key summary mapping.

## `velnora.ops.streaming.StackStats`

`StackStats()` is an accumulator constructor usable with `StatsOfDict`. Its summary is a mapping with `count` (integer) and `samples` (a tensor with a leading draw axis).

## `velnora.infer.Importance`

`Importance(model[, guide, num_samples])` constructs a posterior object; `run(*args, **kwargs)` executes it. `exec_traces` is a sequence of execution traces and `log_weights` is the corresponding sequence of scalar tensors. `get_normalized_weights()` returns a one-dimensional tensor; `get_log_normalizer()` returns a scalar tensor.

## `velnora.infer.SMCFilter`

`SMCFilter(model, guide, num_particles, max_plate_nesting)` accepts objects implementing `init(state, *args, **kwargs)` and `step(state, *args, **kwargs)`. The supplied `state` supports string-keyed tensor lookup and model assignment. Driver `init` and `step` forward their arguments to these callbacks. `get_empirical()` returns a string-to-`Empirical` mapping. Rejected particle counts raise `AssertionError`; a prohibited guide state write raises `RuntimeError`; filtering collapse raises `SMCFailed`.

## `velnora.infer.smcfilter.SMCFailed`

`SMCFailed` is the publicly importable exception class for filtering collapse.

## `velnora.infer.Predictive`

`Predictive(model[, posterior_samples, num_samples, guide, return_sites, parallel])` constructs a callable. `posterior_samples` maps string site names to tensors with leading draw axes; `num_samples` is an integer; `guide` is callable; `return_sites` is a sequence of string names, including `_RETURN` for the model return; `parallel` is boolean. Calling with model arguments returns `dict[str, Tensor]`. Site tensors have a leading draw axis, any singleton population axes, and their site event axes; `_RETURN` carries the model return tensor with the leading draw axis. Rejected construction raises `ValueError`; a draw-count conflict is carried by `UserWarning`.

## `velnora.infer.WeighedPredictive`

`WeighedPredictive(model, guide=guide, num_samples=count, parallel=selection)` constructs a callable. The call accepts `model_guide` as an observation-conditioned model callable. Its result exposes `samples` (a string-to-tensor mapping with leading draw axes), `log_weights` (log importance weights), `model_log_prob` and `guide_log_prob` (log scores), each score tensor shaped `(draws,)`.

## `velnora.ops.stats.quantile`

`quantile(input, probs[, dim])` returns a tensor replacing the selected sample axis by a requested-probability axis; a scalar probability removes that axis. Inputs are tensors, axis parameters are integers, and probability arguments are numeric scalars or sequences.

## `velnora.ops.stats.pi`

`pi(input, prob[, dim])` returns a tensor replacing the selected sample axis by a two-endpoint interval axis. Inputs are tensors, axis parameters are integers, and probability arguments are numeric scalars or sequences.

## `velnora.ops.stats.hpdi`

`hpdi(input, prob[, dim])` returns a tensor replacing the selected sample axis by a two-endpoint interval axis. Inputs are tensors, axis parameters are integers, and probability arguments are numeric scalars or sequences.

## `velnora.ops.stats.weighed_quantile`

`weighed_quantile(input, probs, log_weights[, dim])` returns a tensor replacing the selected sample axis by a requested-probability axis. Inputs are tensors, axis parameters are integers, and probability arguments are numeric scalars or sequences. `log_weights` is a tensor indexed by draw.

## `velnora.ops.stats.effective_sample_size`

`effective_sample_size(input[, chain_dim, sample_dim])` returns a tensor over the remaining event axes containing effective sample counts. Inputs are tensors, axis parameters are integers, and probability arguments are numeric scalars or sequences.

## `velnora.ops.stats.gelman_rubin`

`gelman_rubin(input[, chain_dim, sample_dim])` returns a tensor over the remaining event axes containing convergence diagnostics. Inputs are tensors, axis parameters are integers, and probability arguments are numeric scalars or sequences.

## `velnora.ops.stats.split_gelman_rubin`

`split_gelman_rubin(input[, chain_dim, sample_dim])` returns a tensor over the remaining event axes containing split-chain diagnostics. Inputs are tensors, axis parameters are integers, and probability arguments are numeric scalars or sequences.

## `velnora.ops.stats.autocorrelation`

`autocorrelation(input[, dim])` returns a tensor with the input shape, with the selected axis indexing successive lags starting at zero. Inputs are tensors, axis parameters are integers, and probability arguments are numeric scalars or sequences.

## `velnora.ops.stats.autocovariance`

`autocovariance(input[, dim])` returns a tensor with the input shape, with the selected axis indexing successive lags starting at zero. Inputs are tensors, axis parameters are integers, and probability arguments are numeric scalars or sequences.

## `velnora.ops.stats.crps_empirical`

`crps_empirical(pred, truth)` returns a tensor with the truth shape. Inputs are tensors, axis parameters are integers, and probability arguments are numeric scalars or sequences. `pred` has a leading draw axis before the axes of `truth`.

## `velnora.infer.mcmc.util.summary`

`summary(samples[, prob, group_by_chain])` accepts a string-to-sample-tensor mapping, numeric probability mass and boolean grouping selection. Grouped input has shape `(chains, draws, event_shape...)`; combined input omits the chain axis. It returns a mapping `{site_name: statistics}` with tensor fields `mean` and `std` of the event shape.

## `velnora.distributions.DiscreteHMM`

`DiscreteHMM(initial_logits, transition_logits, observation_dist)` constructs a sequence distribution. Logits and matrices are tensors and distribution-valued arguments are distribution objects. `log_prob(value)` returns floating tensors over sample and batch axes. `filter(value)` returns a categorical distribution with `probs` of shape `batch_shape + (states,)`.

## `velnora.distributions.GaussianHMM`

`GaussianHMM(initial_dist, transition_matrix, transition_dist, observation_matrix, observation_dist[, duration])` constructs a sequence distribution. Logits and matrices are tensors and distribution-valued arguments are distribution objects. Sequence samples have shape `sample_shape + batch_shape + (duration, observation_dim)`; `duration`, when supplied, is an integer. `log_prob(value)` returns floating tensors over sample and batch axes. `rsample(sample_shape)` returns a sequence tensor. `filter(value)` returns a multivariate normal with `mean` shaped `batch_shape + (hidden,)` and `covariance_matrix` shaped `batch_shape + (hidden, hidden)`. `prefix_condition(data)` returns a sequence distribution with `log_prob` and `rsample` on its suffix. Missing sampler duration raises `AssertionError`.

## `velnora.distributions.GammaGaussianHMM`

`GammaGaussianHMM(scale_dist, initial_dist, transition_matrix, transition_dist, observation_matrix, observation_dist)` constructs a sequence distribution. Logits and matrices are tensors and distribution-valued arguments are distribution objects. Sequence samples have shape `sample_shape + batch_shape + (duration, observation_dim)`; `duration`, when supplied, is an integer. `log_prob(value)` returns floating tensors over sample and batch axes. `filter(value)` returns `(Gamma, MultivariateNormal)`; the first exposes batch tensors `concentration` and `rate`, and the second exposes `mean` shaped `batch_shape + (hidden,)`.

## `velnora.distributions.GaussianMRF`

`GaussianMRF(initial_dist, transition_dist, observation_dist)` constructs a sequence distribution. Logits and matrices are tensors and distribution-valued arguments are distribution objects. `log_prob(value)` returns floating tensors over sample and batch axes.

## `velnora.distributions.LinearHMM`

`LinearHMM(initial_dist, transition_matrix, transition_dist, observation_matrix, observation_dist[, duration])` constructs a sequence distribution. Logits and matrices are tensors and distribution-valued arguments are distribution objects. Sequence samples have shape `sample_shape + batch_shape + (duration, observation_dim)`; `duration`, when supplied, is an integer. `rsample(sample_shape)` returns a sequence tensor. Rejected noise distributions raise `AssertionError`.

## `velnora.distributions.IndependentHMM`

`IndependentHMM(base_dist)` constructs a sequence distribution. Logits and matrices are tensors and distribution-valued arguments are distribution objects. Sequence samples have shape `sample_shape + batch_shape + (duration, observation_dim)`; `duration`, when supplied, is an integer. `rsample(sample_shape)` returns a sequence tensor.

## `velnora.contrib.timeseries.IndependentMaternGP`

`IndependentMaternGP(nu[, dt, obs_dim, length_scale_init, kernel_scale_init, obs_noise_scale_init])` constructs a trainable temporal model. Dimensions are integers and scale initializers are tensors. `nu` is numeric. `dt` is numeric. `log_prob(targets)` accepts `(time, outputs)` tensors and returns a tensor of shape `(outputs,)`. `forecast(targets, dts)` returns a distribution exposing `mean` of shape `(horizon, outputs)` and `variance` of shape `(horizon, outputs)`. `dts` is a one-dimensional tensor of future time offsets. `parameters()` yields trainable tensors. `obs_noise_scale` is an output-vector tensor. `kernel.length_scale` and `kernel.kernel_scale` are vector tensors. Unsupported smoothness requests raise `NotImplementedError`.

## `velnora.contrib.timeseries.LinearlyCoupledMaternGP`

`LinearlyCoupledMaternGP(nu[, dt, obs_dim, num_gps, length_scale_init, kernel_scale_init, obs_noise_scale_init])` constructs a trainable temporal model. Dimensions are integers and scale initializers are tensors. `nu` is numeric. `dt` is numeric. `log_prob(targets)` accepts `(time, outputs)` tensors and returns a scalar tensor. `forecast(targets, dts)` returns a distribution exposing `mean` of shape `(horizon, outputs)` and `covariance_matrix` of shape `(horizon, outputs, outputs)` and `variance` of shape `(horizon, outputs)`. `dts` is a one-dimensional tensor of future time offsets. `parameters()` yields trainable tensors. `obs_noise_scale` is an output-vector tensor. `kernel.length_scale` and `kernel.kernel_scale` are vector tensors. `A` is an assignable mixing tensor of shape `(processes, outputs)`. Unsupported smoothness requests raise `NotImplementedError`.

## `velnora.contrib.timeseries.DependentMaternGP`

`DependentMaternGP([nu, dt, obs_dim, length_scale_init, obs_noise_scale_init])` constructs a trainable temporal model. Dimensions are integers and scale initializers are tensors. `nu` is numeric. `dt` is numeric. `log_prob(targets)` accepts `(time, outputs)` tensors and returns a scalar tensor. `forecast(targets, dts)` returns a distribution exposing `mean` of shape `(horizon, outputs)` and `covariance_matrix` of shape `(horizon, outputs, outputs)` and `variance` of shape `(horizon, outputs)`. `dts` is a one-dimensional tensor of future time offsets. `parameters()` yields trainable tensors. `obs_noise_scale` is an output-vector tensor. `kernel.length_scale` and the assignable `wiener_noise_tril` matrix expose covariance parameters. Unsupported smoothness requests raise `NotImplementedError`.

## `velnora.contrib.timeseries.GenericLGSSM`

`GenericLGSSM(obs_dim, state_dim[, obs_noise_scale_init, learnable_observation_loc])` constructs a trainable temporal model. Dimensions are integers, scale initializers are tensors and `learnable_observation_loc` is boolean. `obs_loc` is an output-vector tensor. `log_prob(targets)` accepts `(time, outputs)` tensors and returns a scalar tensor. `forecast(targets, N_timesteps)` returns a distribution exposing `mean` of shape `(horizon, outputs)` and `covariance_matrix` of shape `(horizon, outputs, outputs)` and `variance` of shape `(horizon, outputs)`. `N_timesteps` is an integer forecast length. `parameters()` yields trainable tensors. `obs_noise_scale` is an output-vector tensor. `trans_matrix` and `obs_matrix` are assignable tensors shaped `(hidden, hidden)` and `(hidden, outputs)`. `init_noise_scale_sq` and `trans_noise_scale_sq` are vectors of shape `(hidden,)`.

## `velnora.contrib.timeseries.GenericLGSSMWithGPNoiseModel`

`GenericLGSSMWithGPNoiseModel(obs_dim, state_dim[, obs_noise_scale_init, learnable_observation_loc])` constructs a trainable temporal model. Dimensions are integers, scale initializers are tensors and `learnable_observation_loc` is boolean. `obs_loc` is an output-vector tensor. `log_prob(targets)` accepts `(time, outputs)` tensors and returns a scalar tensor. `forecast(targets, N_timesteps)` returns a distribution exposing `mean` of shape `(horizon, outputs)` and `covariance_matrix` of shape `(horizon, outputs, outputs)` and `variance` of shape `(horizon, outputs)`. `N_timesteps` is an integer forecast length. `parameters()` yields trainable tensors. `obs_noise_scale` is an output-vector tensor. `kernel.length_scale` and `kernel.kernel_scale` are vector tensors. `z_trans_matrix` and `z_obs_matrix` are assignable tensors shaped `(hidden, hidden)` and `(hidden, outputs)`. `init_noise_scale_sq` and `trans_noise_scale_sq` are vectors of shape `(hidden,)`.

## `velnora.contrib.gp.kernels.RBF`

`RBF(input_dim[, variance, lengthscale, active_dims])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. `input_dim` is an integer. `active_dims` is an integer-index list. Numeric covariance arguments are scalars or tensors.

## `velnora.contrib.gp.kernels.Exponential`

`Exponential(input_dim[, variance, lengthscale, active_dims])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. `input_dim` is an integer. `active_dims` is an integer-index list. Numeric covariance arguments are scalars or tensors.

## `velnora.contrib.gp.kernels.RationalQuadratic`

`RationalQuadratic(input_dim[, variance, lengthscale, scale_mixture, active_dims])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. `input_dim` is an integer. `active_dims` is an integer-index list. Numeric covariance arguments are scalars or tensors.

## `velnora.contrib.gp.kernels.Matern32`

`Matern32(input_dim[, variance, lengthscale, active_dims])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. `input_dim` is an integer. `active_dims` is an integer-index list. Numeric covariance arguments are scalars or tensors.

## `velnora.contrib.gp.kernels.Matern52`

`Matern52(input_dim[, variance, lengthscale, active_dims])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. `input_dim` is an integer. `active_dims` is an integer-index list. Numeric covariance arguments are scalars or tensors.

## `velnora.contrib.gp.kernels.Cosine`

`Cosine(input_dim[, variance, lengthscale, active_dims])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. `input_dim` is an integer. `active_dims` is an integer-index list. Numeric covariance arguments are scalars or tensors.

## `velnora.contrib.gp.kernels.Periodic`

`Periodic(input_dim[, variance, lengthscale, period, active_dims])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. `input_dim` is an integer. `active_dims` is an integer-index list. Numeric covariance arguments are scalars or tensors.

## `velnora.contrib.gp.kernels.Linear`

`Linear(input_dim[, variance, active_dims])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. `input_dim` is an integer. `active_dims` is an integer-index list. Numeric covariance arguments are scalars or tensors.

## `velnora.contrib.gp.kernels.Polynomial`

`Polynomial(input_dim[, variance, bias, degree, active_dims])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. `input_dim` is an integer. `degree` is an integer. `active_dims` is an integer-index list. Numeric covariance arguments are scalars or tensors.

## `velnora.contrib.gp.kernels.Brownian`

`Brownian(input_dim[, variance, active_dims])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. `input_dim` is an integer. `active_dims` is an integer-index list. Numeric covariance arguments are scalars or tensors.

## `velnora.contrib.gp.kernels.Constant`

`Constant(input_dim[, variance, active_dims])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. `input_dim` is an integer. `active_dims` is an integer-index list. Numeric covariance arguments are scalars or tensors.

## `velnora.contrib.gp.kernels.WhiteNoise`

`WhiteNoise(input_dim[, variance, active_dims])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. `input_dim` is an integer. `active_dims` is an integer-index list. Numeric covariance arguments are scalars or tensors.

## `velnora.contrib.gp.kernels.Coregionalize`

`Coregionalize(input_dim[, components, diagonal, active_dims])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. `input_dim` is an integer. `active_dims` is an integer-index list. Numeric covariance arguments are scalars or tensors. `components` and `diagonal` are public fitted tensors shaped `(D, rank)` and `(D,)`.

## `velnora.contrib.gp.kernels.Sum`

`Sum(kern0, kern1)` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. Kernel arguments are kernel objects.

## `velnora.contrib.gp.kernels.Product`

`Product(kern0, kern1)` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. Kernel arguments are kernel objects.

## `velnora.contrib.gp.kernels.Exponent`

`Exponent(kern)` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. Kernel arguments are kernel objects.

## `velnora.contrib.gp.kernels.VerticalScaling`

`VerticalScaling(kern, vscaling_fn)` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. Kernel arguments are kernel objects. Scaling/warping arguments are tensor callables.

## `velnora.contrib.gp.kernels.Warping`

`Warping(kern[, iwarping_fn])` constructs a covariance kernel callable as `forward(X[, Z, diag])`. `X` and `Z` are input matrices; the result is a covariance matrix of shape `(N, M)`, or a vector of shape `(N,)` with `diag=True`. Kernel arguments are kernel objects. Scaling/warping arguments are tensor callables.

## `velnora.contrib.gp.likelihoods.Gaussian`

`Gaussian([variance])` constructs a callable likelihood. `forward(f_loc, f_var[, y])` accepts latent location and variance tensors and optional observation tensor, and returns an observation tensor. Returned observations have the latent tensor shape. `variance` is a public scalar tensor.

## `velnora.contrib.gp.likelihoods.Binary`

`Binary([response_function])` constructs a callable likelihood. `forward(f_loc, f_var[, y])` accepts latent location and variance tensors and optional observation tensor, and returns an observation tensor. Returned observations have the latent tensor shape. `response_function` is a tensor callable.

## `velnora.contrib.gp.likelihoods.MultiClass`

`MultiClass(num_classes[, response_function])` constructs a callable likelihood. `forward(f_loc, f_var[, y])` accepts latent location and variance tensors and optional observation tensor, and returns an observation tensor. Latent tensors end in `(classes, observations)`, and the returned observations end in `(observations,)`. `response_function` is a tensor callable.

## `velnora.contrib.gp.likelihoods.Poisson`

`Poisson([response_function])` constructs a callable likelihood. `forward(f_loc, f_var[, y])` accepts latent location and variance tensors and optional observation tensor, and returns an observation tensor. Returned observations have the latent tensor shape. `response_function` is a tensor callable.

## `velnora.contrib.gp.models.GPRegression`

`GPRegression(X, y, kernel[, noise, mean_function, jitter])` constructs a trainable Gaussian process model. `X` is an input matrix; `y` is an observation tensor or `None` and `kernel` is a covariance object. `mean_function` is a tensor callable. `jitter` and `noise` are numeric scalars or scalar tensors. `model` and `guide` are callable probabilistic entries. Prediction is `forward(Xnew[, full_cov, noiseless])`, also available by calling the model. It returns `(location, uncertainty)`: a tensor ending in `(M,)` and a tensor ending in `(M,)` for marginal variances or `(M, M)` for covariance. The selectors are booleans. `set_data(X, y)` accepts replacement tensors. `parameters()` yields trainable tensors. Public fitted attributes include `X`, `y`, `kernel`, `noise`. Incompatible data or prediction shapes raise `ValueError`.

## `velnora.contrib.gp.models.SparseGPRegression`

`SparseGPRegression(X, y, kernel, Xu[, noise, approx, jitter])` constructs a trainable Gaussian process model. `X` and `Xu` are input matrices; `y` is an observation tensor or `None` and `kernel` is a covariance object. `jitter` and `noise` are numeric scalars or scalar tensors. `model` and `guide` are callable probabilistic entries. Prediction is `forward(Xnew[, full_cov, noiseless])`, also available by calling the model. It returns `(location, uncertainty)`: a tensor ending in `(M,)` and a tensor ending in `(M,)` for marginal variances or `(M, M)` for covariance. The selectors are booleans. `set_data(X, y)` accepts replacement tensors. `parameters()` yields trainable tensors. Public fitted attributes include `X`, `y`, `kernel`, `noise`. `Xu` is the inducing-input tensor. `approx` is a string selection. Unsupported approximation requests raise `ValueError`. Incompatible data or prediction shapes raise `ValueError`.

Approximation selections are spelled `DTC`, `FITC` and `VFE`.

## `velnora.contrib.gp.models.VariationalGP`

`VariationalGP(X, y, kernel, likelihood[, latent_shape, jitter])` constructs a trainable Gaussian process model. `X` is an input matrix; `y` is an observation tensor or `None` and `kernel` is a covariance object. `likelihood` is a callable observation object. `jitter` is a numeric scalar. `latent_shape` is a shape tuple. `model` and `guide` are callable probabilistic entries. Prediction is `forward(Xnew[, full_cov])`, also available by calling the model. It returns `(location, uncertainty)`: a tensor ending in `(M,)` and a tensor ending in `(M,)` for marginal variances or `(M, M)` for covariance. The selectors are booleans. `set_data(X, y)` accepts replacement tensors. `parameters()` yields trainable tensors. Public fitted attributes include `X`, `y`, `kernel`, `likelihood`. `f_loc` and `f_scale_tril` are assignable tensors ending in `(B,)` and `(B, B)`. The observation record is named `likelihood.y` and its `fn.base_dist.log_prob(y)` returns a tensor per observation. Incompatible data or prediction shapes raise `ValueError`.

## `velnora.contrib.gp.models.VariationalSparseGP`

`VariationalSparseGP(X, y, kernel, Xu, likelihood[, latent_shape, jitter])` constructs a trainable Gaussian process model. `X` and `Xu` are input matrices; `y` is an observation tensor or `None` and `kernel` is a covariance object. `likelihood` is a callable observation object. `jitter` is a numeric scalar. `latent_shape` is a shape tuple. `model` and `guide` are callable probabilistic entries. Prediction is `forward(Xnew[, full_cov])`, also available by calling the model. It returns `(location, uncertainty)`: a tensor ending in `(M,)` and a tensor ending in `(M,)` for marginal variances or `(M, M)` for covariance. The selectors are booleans. `set_data(X, y)` accepts replacement tensors. `parameters()` yields trainable tensors. Public fitted attributes include `X`, `y`, `kernel`, `likelihood`. `u_loc` and `u_scale_tril` are assignable tensors ending in `(B,)` and `(B, B)`. The observation record is named `likelihood.y` and its `fn.base_dist.log_prob(y)` returns a tensor per observation. `Xu` is the inducing-input tensor. Incompatible data or prediction shapes raise `ValueError`.

## `velnora.contrib.gp.models.GPLVM`

`GPLVM(base_model)` accepts a Gaussian process model and exposes callable `model` and `guide` entries. `X_loc` and `X_scale` are trainable coordinate tensors of shape `(N, D)`. The latent-coordinate trace site is `X`, whose `value` and `log_prob` are tensors.

## `velnora.contrib.forecast.ForecastingModel`

`ForecastingModel` is subclassable. The subclass supplies `model(zero_data, covariates)` and calls `predict(noise_dist, prediction)` with a distribution and a prediction tensor. `zero_data` and `covariates` are tensors with time and feature axes at the right. The subclass can access `time_plate` as a context manager.

## `velnora.contrib.forecast.Forecaster`

`Forecaster(model, data, covariates[, guide, num_steps, log_every, learning_rate, learning_rate_decay, warm_start])` accepts a forecasting model and data/covariate tensors. Calling the forecaster as `(data, covariates, num_samples)` returns a tensor of shape `(draws, group_shape..., future_duration, observation_dimension)`. Counts are integers. Learning settings are numeric, `guide` is a callable and `warm_start` is boolean. Rejected fitting or prediction requests raise `AssertionError`. `losses` is a list of floating values, one entry per fitting step.

## `velnora.contrib.forecast.HMCForecaster`

`HMCForecaster(model, data, covariates[, num_warmup, num_samples, max_tree_depth])` accepts a forecasting model and data/covariate tensors. Calling the forecaster as `(data, covariates, num_samples)` returns a tensor of shape `(draws, group_shape..., future_duration, observation_dimension)`. Counts are integers. Rejected fitting or prediction requests raise `AssertionError`.

## `velnora.contrib.forecast.backtest`

`backtest(data, covariates, model_fn[, metrics, transform, train_window, min_train_window, test_window, min_test_window, stride, num_samples, forecaster_options])` returns a list of row dictionaries. Data and covariates are tensors; `model_fn` constructs a forecasting model. Window and stride arguments are integers; `forecaster_options` is a constructor-settings mapping. `metrics` maps caller-selected string keys to callbacks `(pred, truth) -> numeric_scalar`. `transform(pred, truth)` returns a tensor pair. Callback `pred` has shape `(draws, evaluation_duration, observation_dimension)` and `truth` has shape `(evaluation_duration, observation_dimension)`. Rows expose integer `t0`, `t1` and `t2` denoting training start, evaluation start and evaluation end offsets, integer `num_samples`, and floating `mae`, `rmse` and `crps` fields when those metrics are selected, or caller-selected metric keys. Rejected warm-start/window combinations raise `ValueError`.

## `velnora.contrib.forecast.evaluate.eval_mae`

`eval_mae(pred, truth)` accepts predictive tensors with leading draw axis and observation tensors and returns a Python floating scalar metric.

## `velnora.contrib.forecast.evaluate.eval_rmse`

`eval_rmse(pred, truth)` accepts predictive tensors with leading draw axis and observation tensors and returns a Python floating scalar metric.

## `velnora.contrib.forecast.evaluate.eval_crps`

`eval_crps(pred, truth)` accepts predictive tensors with leading draw axis and observation tensors and returns a Python floating scalar metric.

## `velnora.contrib.epidemiology.CompartmentalModel`

`CompartmentalModel(compartments, duration, population)` is subclassable. `compartments` is a sequence of string names, `duration` is an integer, and `population` is a scalar integer or a region-vector tensor. Subclasses supply `global_model()`, `initialize(params)` returning a compartment-to-value mapping, and `transition(params, state, t)` updating a compartment-state mapping, where `t` is a time index or slice. Public `population`, `duration`, `compartments` and `is_regional` expose the declaration. Rejected declarations raise `AssertionError`.

`generate(fixed)` accepts a string-to-tensor mapping and returns a string-to-tensor mapping of sampled global values and trajectories. `fit_svi(num_samples=..., num_steps=..., num_particles=..., learning_rate=..., learning_rate_decay=..., guide_rank=..., jit=..., log_every=...)` and `fit_mcmc(num_samples=..., warmup_steps=..., num_quant_bins=..., max_tree_depth=..., disable_progbar=...)` expose fitted draws through the public `samples` mapping. `predict(forecast=...)` returns a string-to-tensor mapping with a leading draw axis and a time axis on trajectories. Calling prediction without fitted state raises `RuntimeError` or `AttributeError`.

The custom-model mapping carries caller-named global values and compartments. `max_plate_nesting` is an integer number of reserved population axes available to callers declaring additional populations.

## `velnora.contrib.epidemiology.models.SimpleSIRModel`

`SimpleSIRModel(population, recovery_time, data)` constructs a compartment model exposing `generate`, `fit_svi`, `fit_mcmc`, `predict` and `samples`. Biological durations are numeric; `data` is a time-indexed sequence of observations or missing entries. Rejected constructor inputs raise `AssertionError`. Returned mappings expose `S`, `I`, `S2I`, `I2R`, `obs`, `R0`, `rho`. Compartment, transition and observation trajectories have a time axis followed by a region axis for regional models; fitted predictions prepend a draw axis. Global parameters are scalar or region tensors, with a leading draw axis in predictions. Compartment keys denote compartment counts, transition keys denote directed flows, `obs` denotes reports, `R0` reproduction, `rho` reporting, and additional named fields denote the corresponding variant quantities.

## `velnora.contrib.epidemiology.models.SimpleSEIRModel`

`SimpleSEIRModel(population, incubation_time, recovery_time, data)` constructs a compartment model exposing `generate`, `fit_svi`, `fit_mcmc`, `predict` and `samples`. Biological durations are numeric; `data` is a time-indexed sequence of observations or missing entries. Rejected constructor inputs raise `AssertionError`. Returned mappings expose `S`, `E`, `I`, `S2E`, `E2I`, `I2R`, `obs`, `R0`, `rho`. Compartment, transition and observation trajectories have a time axis followed by a region axis for regional models; fitted predictions prepend a draw axis. Global parameters are scalar or region tensors, with a leading draw axis in predictions. Compartment keys denote compartment counts, transition keys denote directed flows, `obs` denotes reports, `R0` reproduction, `rho` reporting, and additional named fields denote the corresponding variant quantities.

## `velnora.contrib.epidemiology.models.SimpleSEIRDModel`

`SimpleSEIRDModel(population, incubation_time, recovery_time, mortality_rate, data)` constructs a compartment model exposing `generate`, `fit_svi`, `fit_mcmc`, `predict` and `samples`. Biological durations and mortality are numeric; `data` is a time-indexed sequence of observations or missing entries. Rejected constructor inputs raise `AssertionError`. Returned mappings expose `S`, `E`, `I`, `D`, `S2E`, `E2I`, `I2R`, `I2D`, `obs`, `R0`, `rho`. Compartment, transition and observation trajectories have a time axis followed by a region axis for regional models; fitted predictions prepend a draw axis. Global parameters are scalar or region tensors, with a leading draw axis in predictions. Compartment keys denote compartment counts, transition keys denote directed flows, `obs` denotes reports, `R0` reproduction, `rho` reporting, and additional named fields denote the corresponding variant quantities.

## `velnora.contrib.epidemiology.models.OverdispersedSIRModel`

`OverdispersedSIRModel(population, recovery_time, data)` constructs a compartment model exposing `generate`, `fit_svi`, `fit_mcmc`, `predict` and `samples`. Biological durations are numeric; `data` is a time-indexed sequence of observations or missing entries. Rejected constructor inputs raise `AssertionError`. Returned mappings expose `S`, `I`, `S2I`, `I2R`, `obs`, `R0`, `rho`, `od`. Compartment, transition and observation trajectories have a time axis followed by a region axis for regional models; fitted predictions prepend a draw axis. Global parameters are scalar or region tensors, with a leading draw axis in predictions. Compartment keys denote compartment counts, transition keys denote directed flows, `obs` denotes reports, `R0` reproduction, `rho` reporting, and additional named fields denote the corresponding variant quantities.

## `velnora.contrib.epidemiology.models.OverdispersedSEIRModel`

`OverdispersedSEIRModel(population, incubation_time, recovery_time, data)` constructs a compartment model exposing `generate`, `fit_svi`, `fit_mcmc`, `predict` and `samples`. Biological durations are numeric; `data` is a time-indexed sequence of observations or missing entries. Rejected constructor inputs raise `AssertionError`. Returned mappings expose `S`, `E`, `I`, `S2E`, `E2I`, `I2R`, `obs`, `R0`, `rho`, `od`. Compartment, transition and observation trajectories have a time axis followed by a region axis for regional models; fitted predictions prepend a draw axis. Global parameters are scalar or region tensors, with a leading draw axis in predictions. Compartment keys denote compartment counts, transition keys denote directed flows, `obs` denotes reports, `R0` reproduction, `rho` reporting, and additional named fields denote the corresponding variant quantities.

## `velnora.contrib.epidemiology.models.SuperspreadingSIRModel`

`SuperspreadingSIRModel(population, recovery_time, data)` constructs a compartment model exposing `generate`, `fit_svi`, `fit_mcmc`, `predict` and `samples`. Biological durations are numeric; `data` is a time-indexed sequence of observations or missing entries. Rejected constructor inputs raise `AssertionError`. Returned mappings expose `S`, `I`, `S2I`, `I2R`, `obs`, `R0`, `rho`, `k`. Compartment, transition and observation trajectories have a time axis followed by a region axis for regional models; fitted predictions prepend a draw axis. Global parameters are scalar or region tensors, with a leading draw axis in predictions. Compartment keys denote compartment counts, transition keys denote directed flows, `obs` denotes reports, `R0` reproduction, `rho` reporting, and additional named fields denote the corresponding variant quantities.

## `velnora.contrib.epidemiology.models.SuperspreadingSEIRModel`

`SuperspreadingSEIRModel(population, incubation_time, recovery_time, data)` constructs a compartment model exposing `generate`, `fit_svi`, `fit_mcmc`, `predict` and `samples`. Biological durations are numeric; `data` is a time-indexed sequence of observations or missing entries. Rejected constructor inputs raise `AssertionError`. Returned mappings expose `S`, `E`, `I`, `S2E`, `E2I`, `I2R`, `obs`, `R0`, `rho`, `k`. Compartment, transition and observation trajectories have a time axis followed by a region axis for regional models; fitted predictions prepend a draw axis. Global parameters are scalar or region tensors, with a leading draw axis in predictions. Compartment keys denote compartment counts, transition keys denote directed flows, `obs` denotes reports, `R0` reproduction, `rho` reporting, and additional named fields denote the corresponding variant quantities.

## `velnora.contrib.epidemiology.models.HeterogeneousSIRModel`

`HeterogeneousSIRModel(population, recovery_time, data)` constructs a compartment model exposing `generate`, `fit_svi`, `fit_mcmc`, `predict` and `samples`. Biological durations are numeric; `data` is a time-indexed sequence of observations or missing entries. Rejected constructor inputs raise `AssertionError`. Returned mappings expose `S`, `I`, `S2I`, `I2R`, `obs`, `R0`, `beta`, `Rt`, `rho0`, `rho1`, `rho2`. Compartment, transition and observation trajectories have a time axis followed by a region axis for regional models; fitted predictions prepend a draw axis. Global parameters are scalar or region tensors, with a leading draw axis in predictions. Compartment keys denote compartment counts, transition keys denote directed flows, `obs` denotes reports, `R0` reproduction, `rho` reporting, and additional named fields denote the corresponding variant quantities.

## `velnora.contrib.epidemiology.models.SparseSIRModel`

`SparseSIRModel(population, recovery_time, data, mask)` constructs a compartment model exposing `generate`, `fit_svi`, `fit_mcmc`, `predict` and `samples`. Biological durations are numeric; `data` is a time-indexed sequence of observations or missing entries. `mask` is a boolean tensor. Rejected constructor inputs raise `AssertionError`. Returned mappings expose `S`, `I`, `O`, `S2I`, `I2R`, `S2O`, `obs`, `R0`, `rho`. Compartment, transition and observation trajectories have a time axis followed by a region axis for regional models; fitted predictions prepend a draw axis. Global parameters are scalar or region tensors, with a leading draw axis in predictions. Compartment keys denote compartment counts, transition keys denote directed flows, `obs` denotes reports, `R0` reproduction, `rho` reporting, and additional named fields denote the corresponding variant quantities.

## `velnora.contrib.epidemiology.models.UnknownStartSIRModel`

`UnknownStartSIRModel(population, recovery_time, pre_obs_window, data)` constructs a compartment model exposing `generate`, `fit_svi`, `fit_mcmc`, `predict` and `samples`. Biological durations are numeric; `data` is a time-indexed sequence of observations or missing entries. Rejected constructor inputs raise `AssertionError`. Returned mappings expose `S`, `I`, `S2I`, `I2R`, `obs`, `R0`, `rho0`, `rho1`, `first_infection`. Compartment, transition and observation trajectories have a time axis followed by a region axis for regional models; fitted predictions prepend a draw axis. Global parameters are scalar or region tensors, with a leading draw axis in predictions. Compartment keys denote compartment counts, transition keys denote directed flows, `obs` denotes reports, `R0` reproduction, `rho` reporting, and additional named fields denote the corresponding variant quantities.

## `velnora.contrib.epidemiology.models.RegionalSIRModel`

`RegionalSIRModel(population, coupling, recovery_time, data)` constructs a compartment model exposing `generate`, `fit_svi`, `fit_mcmc`, `predict` and `samples`. Biological durations are numeric; `data` is a time-indexed sequence of observations or missing entries. `coupling` is a region matrix. Rejected constructor inputs raise `AssertionError`. Returned mappings expose `S`, `I`, `S2I`, `I2R`, `obs`, `R0`, `rho`, `rho_c0`, `rho_c1`. Compartment, transition and observation trajectories have a time axis followed by a region axis for regional models; fitted predictions prepend a draw axis. Global parameters are scalar or region tensors, with a leading draw axis in predictions. Compartment keys denote compartment counts, transition keys denote directed flows, `obs` denotes reports, `R0` reproduction, `rho` reporting, and additional named fields denote the corresponding variant quantities.

## `velnora.contrib.epidemiology.models.HeterogeneousRegionalSIRModel`

`HeterogeneousRegionalSIRModel(population, coupling, recovery_time, data)` constructs a compartment model exposing `generate`, `fit_svi`, `fit_mcmc`, `predict` and `samples`. Biological durations are numeric; `data` is a time-indexed sequence of observations or missing entries. `coupling` is a region matrix. Rejected constructor inputs raise `AssertionError`. Returned mappings expose `S`, `I`, `S2I`, `I2R`, `obs`, `R0`, `rho0`, `rho`, `rho_shift`, `R_drift`, `rho_drift`, `R_factor`, `Rt`. Compartment, transition and observation trajectories have a time axis followed by a region axis for regional models; fitted predictions prepend a draw axis. Global parameters are scalar or region tensors, with a leading draw axis in predictions. Compartment keys denote compartment counts, transition keys denote directed flows, `obs` denotes reports, `R0` reproduction, `rho` reporting, and additional named fields denote the corresponding variant quantities.

## `velnora.contrib.epidemiology.models`

The model classes are exposed by `velnora.contrib.epidemiology.models`. Time-addressed trace records have the form `<name>_<time>`: transition names `S2I`, `S2E`, `E2I`, `I2R`, `I2D`, `S2O`; report name `obs`; and variant names `beta`, `R_factor` and `rho_shift`. The `fn` field exposes a distribution callable through `log_prob(value)`. Global parameter names are the mapping field names. `first_infection` is an integer-valued time tensor.

Global fields use `R0` for reproduction, `rho` and `rho0`, `rho1`, `rho2` for reporting quantities, `od` for dispersion, `k` for superspreading concentration, `rho_c0` and `rho_c1` for reporting concentrations, and `R_drift` and `rho_drift` for drift scales. Temporal fields use `beta` for a transmission multiplier, `Rt` for reproduction, `R_factor` for a shared transmission factor, `rho_shift` for regional reporting shifts, and `rho` for regional reporting probabilities.

## `velnora.contrib.epidemiology.distributions.binomial_dist`

`binomial_dist(total_count, probs)` accepts numeric or tensor count and probability parameters and returns a distribution usable by `sample` and `log_prob`.

## `velnora.contrib.oed.eig.nmc_eig`

`nmc_eig(model, design, observation_labels, target_labels[, N, M])` accepts a callable model, a design tensor, and lists of observation and target string labels. The sample counts are integers. It returns an estimate tensor with the design batch shape.

## `velnora.contrib.oed.eig.posterior_eig`

`posterior_eig(model, design, observation_labels, target_labels, num_samples, num_steps, guide, optim[, return_history, final_design, final_num_samples, eig])` accepts a callable model, a design tensor, and lists of observation and target string labels. Counts are integers or estimator-specific sample-count pairs, `optim` is an optimizer wrapper and selection arguments are booleans. It returns an estimate tensor with the design batch shape. The history return form is `(history, estimate)`; `history` has a leading training-step axis before the design batch axes. A final-design tensor and final evaluation count, where supplied, use `final_design` and `final_num_samples`. The `guide` callback is called as `(observations, design, observation_labels, target_labels)`, where `observations` maps labels to tensors. A nonfinite-objective rejection raises `ArithmeticError`. The design tensor and sampled callback tensors preserve the design batch axes after leading sampling axes. The optimizer accepts an iterable of parameter tensors when called; an optimizer with a callable `step()` is also supported.

## `velnora.contrib.oed.eig.marginal_eig`

`marginal_eig(model, design, observation_labels, target_labels, num_samples, num_steps, guide, optim[, return_history, final_num_samples])` accepts a callable model, a design tensor, and lists of observation and target string labels. Counts are integers or estimator-specific sample-count pairs, `optim` is an optimizer wrapper and selection arguments are booleans. It returns an estimate tensor with the design batch shape. With `return_history` selected, the result is `(history, estimate)`; `history` has a leading training-step axis before the design batch axes. A final evaluation count, where supplied, uses `final_num_samples`. The marginal callback is called as `(design, observation_labels, target_labels)`. The design tensor and sampled callback tensors preserve the design batch axes after leading sampling axes. The optimizer accepts an iterable of parameter tensors when called; an optimizer with a callable `step()` is also supported.

## `velnora.contrib.oed.eig.marginal_likelihood_eig`

`marginal_likelihood_eig(model, design, observation_labels, target_labels, num_samples, num_steps, marginal_guide, cond_guide, optim[, return_history, final_num_samples])` accepts a callable model, a design tensor, and lists of observation and target string labels. Counts are integers or estimator-specific sample-count pairs, `optim` is an optimizer wrapper and selection arguments are booleans. It returns an estimate tensor with the design batch shape. With `return_history` selected, the result is `(history, estimate)`; `history` has a leading training-step axis before the design batch axes. A final evaluation count, where supplied, uses `final_num_samples`. The marginal callback is called as `(design, observation_labels, target_labels)`. The conditional callback is called as `(targets, design, observation_labels, target_labels)` with a target-to-tensor mapping. The design tensor and sampled callback tensors preserve the design batch axes after leading sampling axes. The optimizer accepts an iterable of parameter tensors when called; an optimizer with a callable `step()` is also supported.

## `velnora.contrib.oed.eig.vnmc_eig`

`vnmc_eig(model, design, observation_labels, target_labels, num_samples, num_steps, guide, optim[, return_history, final_num_samples])` accepts a callable model, a design tensor, and lists of observation and target string labels. Counts are integers or estimator-specific sample-count pairs, `optim` is an optimizer wrapper and selection arguments are booleans. It returns an estimate tensor with the design batch shape. With `return_history` selected, the result is `(history, estimate)`; `history` has a leading training-step axis before the design batch axes. A final evaluation count, where supplied, uses `final_num_samples`. The `guide` callback is called as `(observations, design, observation_labels, target_labels)`, where `observations` maps labels to tensors. The design tensor and sampled callback tensors preserve the design batch axes after leading sampling axes. The optimizer accepts an iterable of parameter tensors when called; an optimizer with a callable `step()` is also supported.

## `velnora.contrib.oed.eig.lfire_eig`

`lfire_eig(model, design, observation_labels, target_labels, num_y_samples, num_theta_samples, num_steps, classifier, optim[, return_history, final_num_samples])` accepts a callable model, a design tensor, and lists of observation and target string labels. Counts are integers or estimator-specific sample-count pairs, `optim` is an optimizer wrapper and selection arguments are booleans. It returns an estimate tensor with the design batch shape. With `return_history` selected, the result is `(history, estimate)`; `history` has leading training-step and target-population axes before the design batch axes. A final evaluation count, where supplied, uses `final_num_samples`. The score callback is called as `(design, trace, observation_labels, target_labels)` and returns a score tensor; `trace.nodes[name]["value"]` carries its sampled tensors. The design tensor and sampled callback tensors preserve the design batch axes after leading sampling axes. The optimizer accepts an iterable of parameter tensors when called; an optimizer with a callable `step()` is also supported.

## `velnora.contrib.oed.eig.donsker_varadhan_eig`

`donsker_varadhan_eig(model, design, observation_labels, target_labels, num_samples, num_steps, T, optim[, return_history, final_num_samples])` accepts a callable model, a design tensor, and lists of observation and target string labels. Counts are integers or estimator-specific sample-count pairs, `optim` is an optimizer wrapper and selection arguments are booleans. It returns an estimate tensor with the design batch shape. With `return_history` selected, the result is `(history, estimate)`; `history` has a leading training-step axis before the design batch axes. A final evaluation count, where supplied, uses `final_num_samples`. The score callback is called as `(design, trace, observation_labels, target_labels)` and returns a score tensor; `trace.nodes[name]["value"]` carries its sampled tensors. The design tensor and sampled callback tensors preserve the design batch axes after leading sampling axes. The optimizer accepts an iterable of parameter tensors when called; an optimizer with a callable `step()` is also supported.

## `velnora.contrib.tracking.dynamic_models.NcpContinuous`

`NcpContinuous(dimension, sv2)` constructs a motion model accepted by `EKFState`. The dimension is integer and the noise-variance argument is numeric.

## `velnora.contrib.tracking.dynamic_models.NcpDiscrete`

`NcpDiscrete(dimension, sv2)` constructs a motion model accepted by `EKFState`. The dimension is integer and the noise-variance argument is numeric.

## `velnora.contrib.tracking.dynamic_models.NcvContinuous`

`NcvContinuous(dimension, sa2)` constructs a motion model accepted by `EKFState`. The dimension is integer and the noise-variance argument is numeric.

## `velnora.contrib.tracking.dynamic_models.NcvDiscrete`

`NcvDiscrete(dimension, sa2)` constructs a motion model accepted by `EKFState`. The dimension is integer and the noise-variance argument is numeric.

## `velnora.contrib.tracking.extended_kalman_filter.EKFState`

`EKFState(dynamic_model, mean, cov[, time, frame_num])` accepts a motion model, a state vector, a covariance matrix, numeric time and integer frame designation. Readable `mean` and `cov` are tensors; `time` is numeric and `frame_num` is an integer or `None`. Missing time information raises `ValueError`. `predict([dt, destination_time])` returns an `EKFState`. An invalid time request raises `AssertionError`.

`innovation(measurement)` returns `(residual, covariance)` tensors shaped `(position_dimension,)` and `(position_dimension, position_dimension)`. `log_likelihood_of_update(measurement)` returns a scalar tensor. `update(measurement)` returns `(state, (residual, covariance))`. Time-mismatch failures raise `AssertionError`.

## `velnora.contrib.tracking.measurements.PositionMeasurement`

`PositionMeasurement(mean, cov[, time])` accepts a position-vector tensor, measurement covariance tensor and numeric time and returns a measurement object for state-update methods.

## `velnora.contrib.tracking.assignment.MarginalAssignment`

`MarginalAssignment(exists_logits, assign_logits[, bp_iters])` accepts floating log-factor tensors and integer approximation effort. The result exposes `exists_dist.probs` shaped `(objects,)` and `assign_dist.probs` shaped `detection_shape + (objects + 1,)`. The last assignment category denotes a spurious detection; preceding categories correspond to object indices.

`assign_logits` may contain negative infinity to represent omitted edges in the dense input.

## `velnora.contrib.tracking.assignment.MarginalAssignmentPersistent`

`MarginalAssignmentPersistent(exists_logits, assign_logits[, bp_iters, bp_momentum])` accepts floating log-factor tensors and integer approximation effort. The result exposes `exists_dist.probs` shaped `(objects,)` and `assign_dist.probs` shaped `detection_shape + (objects + 1,)`. The last assignment category denotes a spurious detection; preceding categories correspond to object indices. Input assignment factors have frame, detection and object axes; `bp_momentum` is numeric.

## `velnora.contrib.tracking.assignment.MarginalAssignmentSparse`

`MarginalAssignmentSparse(num_objects, num_detections, edges, exists_logits, assign_logits, bp_iters)` accepts floating log-factor tensors and integer approximation effort. The result exposes `exists_dist.probs` shaped `(objects,)` and `assign_dist.probs` shaped `detection_shape + (objects + 1,)`. The last assignment category denotes a spurious detection; preceding categories correspond to object indices. `edges` is an integer tensor shaped `(2, edges)` whose first row contains detection indices and second row contains object indices; `assign_logits` is indexed by edge.

## `velnora.contrib.cevae.CEVAE`

`CEVAE(feature_dim[, outcome_dist, latent_dim, hidden_dim, num_layers, num_samples])` constructs a trainable causal model. Dimensions, layer count and sample count are integers; `outcome_dist` is a string selection. `parameters()` yields trainable tensors. `fit(x, t, y[, num_epochs, batch_size, learning_rate, learning_rate_decay, weight_decay, log_every])` accepts covariate, treatment and outcome tensors and returns a list of numeric per-individual losses in training-step order. `whiten(x)` returns a covariate tensor in fitted input coordinates. `ite(x[, num_samples, batch_size])` returns a tensor with one effect per input individual. Invalid construction raises `ValueError`; incompatible prediction data raises `AssertionError`.

Public `model` and `guide` attributes are callable with `(x, t, y)` and expose conditional distribution entries. `model.z_dist()`, `model.x_dist(z)`, `model.t_dist(z)` and `model.y_dist(t, z)` return distributions. `guide.t_dist(x)`, `guide.y_dist(t, x)` and `guide.z_dist(y, t, x)` return distributions. They expose `log_prob`, `mean`, and their `probs`, `loc`, `scale`, `rate` or `df` parameters as applicable; vector distributions expose `base_dist` and `event_shape`. Model/guide traces expose named `z`, `x`, `t` and `y` records as applicable. The model supports `parameters()`. A fitted object can be saved and restored through `torch.save` and `torch.load` at a supplied path.

Outcome-family selections are spelled `bernoulli`, `exponential`, `laplace`, `normal` and `studentt`.

## `velnora.contrib.cevae.TraceCausalEffect_ELBO`

`TraceCausalEffect_ELBO()` constructs an objective with `differentiable_loss(model, guide, x, t, y)` returning a scalar differentiable tensor and `loss(model, guide, x, t, y)` returning a numeric scalar.

## `velnora.contrib.mue.dataloaders.BiosequenceDataset`

`BiosequenceDataset(source[, source_type, alphabet, max_length, include_stop])` accepts an in-memory sequence collection or a FASTA path. `source_type` is a string selection; `alphabet` is a named alphabet or a string of symbols, `max_length` is an integer and `include_stop` is boolean. Public `alphabet` is a symbol array, `max_length` is an integer, `seq_data` is a tensor shaped `(sequence, padded_position, category)`, and `L_data` is a tensor of sequence lengths. `len(dataset)` returns the sequence count and `dataset[index]` returns `(encoded_sequence, length)`. Encoded rows are categorical indicator vectors with all-zero rows for missing or padded positions; the category axis follows `alphabet`.

Source selections are spelled `list` and `fasta`. Built-in alphabet selections are spelled `amino-acid` and `dna`; the stop symbol is `*`.

FASTA input consists of header lines beginning with `>` followed by sequence-symbol lines. A record can span multiple sequence lines.

## `velnora.contrib.mue.missingdatahmm.MissingDataDiscreteHMM`

`MissingDataDiscreteHMM(initial_logits, transition_logits, observation_logits)` accepts tensor categorical log weights. `log_prob(value)` returns batch log-probability tensors for encoded sequence observations. `filter(value)` and `smooth(value)` return log-probability tensors shaped `(batch, position, state)`, including a singleton batch axis for unbatched parameters.

## `velnora.contrib.mue.statearrangers.Profile`

`Profile(M)` accepts an integer latent sequence length. `forward(precursor_seq_logits, insert_seq_logits, insert_logits, delete_logits[, substitute_logits])` accepts tensor log weights for residues, insertions, insertion decisions, deletion decisions and optional substitutions. It returns `(initial_logits, transition_logits, observation_logits)` tensors shaped `(states,)`, `(states, states)` and `(states, categories)`.

Decision inputs have axes `(position, previous_action, decision)`. The previous-action axis is match, insertion, deletion; the decision axis is no-event, event. Residue inputs have position and category axes; insertion-residue inputs include the final insertion position.

## `velnora.contrib.mue.models.ProfileHMM`

`ProfileHMM(latent_seq_length, alphabet_length[, prior_scale, indel_prior_bias])` constructs a sequence model. Dimension arguments are integers and prior scales and biases are numeric. Invalid dimensions raise `AssertionError`. `fit_svi(dataset, epochs=..., batch_size=...)` returns a list of numeric losses. `evaluate(dataset_train, dataset_test)` returns the numeric four-tuple `(train_evidence, test_evidence, train_perplexity, test_perplexity)`. `model` and `guide` are callable with a sequence tensor; a local weight is additionally accepted by positional argument. Trace record `obs_seq` exposes an observation distribution through `fn.log_prob(data)` with one result per sequence. Public `latent_seq_length` is an integer. Named sample records `precursor_seq`, `insert_seq`, `insert` and `delete` expose tensor `value` and distribution `fn` fields. Guide distributions expose `base_dist.loc` and `base_dist.scale`.

## `velnora.contrib.mue.models.FactorMuE`

`FactorMuE(data_length, alphabet_length, z_dim[, latent_seq_length, indel_factor_dependence, indel_prior_scale, indel_prior_bias, inverse_temp_prior, z_prior_distribution, ARD_prior, substitution_matrix, latent_alphabet_length, weights_prior_scale, offset_prior_scale, substitution_prior_scale])` constructs a sequence model. Dimension arguments are integers, prior scales and biases are numeric, option selections are boolean, and `z_prior_distribution` is a string selection. A dimension refusal raises `AssertionError`. `fit_svi(dataset, epochs=..., batch_size=...)` returns a list of numeric losses. `evaluate(dataset_train, dataset_test)` returns the numeric four-tuple `(train_evidence, test_evidence, train_perplexity, test_perplexity)`. `model` and `guide` are callable with a sequence tensor; a local weight and local-prior weight are additionally accepted by positional arguments. Trace record `obs_seq` exposes an observation distribution through `fn.log_prob(data)` with one result per sequence. Public `latent_seq_length`, `latent_alphabet_length` and `z_dim` are integers. `embed(dataset, batch_size=...)` returns `(locations, scales)` tensors shaped `(sequences, coordinates)`. `decoder(z, W, B, inverse_temp)` returns a mapping with `precursor_seq_logits` and `insert_seq_logits` tensors shaped `(batch, latent_position, latent_category)` and `(batch, insertion_position, latent_category)`, and `insert_logits` and `delete_logits` tensors for coordinate-dependent decisions, shaped `(batch, latent_position, previous_action, decision)`. Named sample records `W`, `B`, `inverse_temp`, `latent`, `alpha`, `insert`, `delete` and `substitute` expose tensors and distributions as applicable to selected options. The latent guide distribution exposes `base_dist.loc` and `base_dist.scale` tensors shaped `(batch, coordinates)`.

The coordinate-prior selections are spelled `Normal` and `Laplace`. Public `indel_factor_dependence` and `substitution_matrix` are boolean selections, and `z_prior_distribution` is the coordinate-prior string.

`decoder` inputs use `z` shaped `(batch, coordinates)`, `W` shaped `(coordinates, width)`, `B` shaped `(width,)` and scalar `inverse_temp`. The width axes group precursor residues before insertion residues; each group is ordered by position then category. With coordinate-dependent indels, insertion-decision and deletion-decision groups follow, each ordered by position, previous action, then decision. The previous-action axis is match, insertion, deletion, and the decision axis is no-event, event. The decoder fields ending in `_logits` are log-probability tensors.

`indel_prior_scale` and `indel_prior_bias` are numeric constructor arguments.

## `velnora.contrib.mue.dataloaders.write`

`write(x, alphabet, file[, truncate_stop, append])` accepts an encoded sequence tensor with sequence, position and category axes, a symbol array and a caller-supplied destination path. Options are booleans. The file contains FASTA records of the form `>{header}\n{sequence}\n`, with each header line followed by its sequence symbols.

## `velnora.distributions.OneHotCategorical`

`OneHotCategorical(probs=...)` accepts a probability tensor and returns a distribution with tensor `sample` and `log_prob` calls and an event axis for categories.

## `velnora`

The module exposes `param`, `sample`, `factor`, `deterministic`, `plate`, `subsample`, `markov`, `get_param_store`, `clear_param_store`, `set_rng_seed`, `enable_validation`, `validation_enabled`.

## `velnora.poutine`

The module exposes `trace`, `condition`, `uncondition`, `replay`, `do`, `block`, `substitute`, `lift`, `scale`, `mask`, `seed`, `reparam`.

## `velnora.infer`

The module exposes `SVI`, `Trace_ELBO`, `TraceMeanField_ELBO`, `TraceEnum_ELBO`, `EnergyDistance`, `Importance`, `SMCFilter`, `Predictive`, `WeighedPredictive`, `config_enumerate`, `infer_discrete`.

## `velnora.nn`

The module exposes `VelnoraModule`, `VelnoraParam`, `VelnoraSample`, `DenseNN`, `ConditionalDenseNN`, `AutoRegressiveNN`, `ConditionalAutoRegressiveNN`.

## `velnora.infer.autoguide`

The module exposes `AutoDelta`, `AutoNormal`, `AutoDiagonalNormal`, `AutoMultivariateNormal`, `AutoLowRankMultivariateNormal`, `AutoNormalizingFlow`, `AutoIAFNormal`, `AutoGuideList`, `AutoStructured`, `AutoGaussian`, `AutoDiscreteParallel`, `AutoLaplaceApproximation`, `init_to_value`.

## `velnora.infer.mcmc`

The module exposes `HMC`, `NUTS`, `RandomWalkKernel`, `MCMC`, `StreamingMCMC`.

## `velnora.infer.reparam`

The module exposes `LocScaleReparam`, `TransformReparam`, `StudentTReparam`, `LatentStableReparam`, `ProjectedNormalReparam`, `DiscreteCosineReparam`, `HaarReparam`, `SplitReparam`.

## `velnora.distributions.transforms`

The module exposes `affine_autoregressive`, `affine_coupling`, `batchnorm`, `block_autoregressive`, `neural_autoregressive`, `planar`, `polynomial`, `radial`, `spline`, `spline_autoregressive`, `spline_coupling`, `sylvester`, `conditional_affine_autoregressive`, `conditional_affine_coupling`, `conditional_neural_autoregressive`, `conditional_planar`, `conditional_radial`, `conditional_spline`, `conditional_spline_autoregressive`, `AffineTransform`, `ExpTransform`, `OrderedTransform`, `ComposeTransform`, `TanhTransform`, `transform_to`.

## `velnora.optim`

The module exposes `VelnoraOptim`, `VelnoraLRScheduler`, `Adam`, `SGD`.

## `velnora.optim.multi`

The module exposes `MixedMultiOptimizer`, `Newton`.

## `velnora.ops`

The module exposes `stats`.

## `velnora.ops.indexing`

The module exposes `Vindex`.

## `velnora.ops.newton`

The module exposes `newton_step`.

## `velnora.ops.streaming`

The module exposes `StatsOfDict`, `StackStats`.

## `velnora.ops.stats`

The module exposes `quantile`, `pi`, `hpdi`, `weighed_quantile`, `effective_sample_size`, `gelman_rubin`, `split_gelman_rubin`, `autocorrelation`, `autocovariance`, `crps_empirical`.

## `velnora.infer.inspect`

The module exposes `get_dependencies`.

## `velnora.infer.mcmc.util`

The module exposes `summary`.

## `velnora.infer.smcfilter`

The module exposes `SMCFailed`.

## `velnora.contrib.bnn`

The module exposes `HiddenLayer`.

## `velnora.contrib.cevae`

The module exposes `CEVAE`, `TraceCausalEffect_ELBO`.

## `velnora.contrib.epidemiology`

The module exposes `CompartmentalModel`, `models`.

## `velnora.contrib.epidemiology.distributions`

The module exposes `binomial_dist`.

## `velnora.contrib.forecast`

The module exposes `ForecastingModel`, `Forecaster`, `HMCForecaster`, `backtest`.

## `velnora.contrib.forecast.evaluate`

The module exposes `eval_mae`, `eval_rmse`, `eval_crps`.

## `velnora.contrib.gp`

The module exposes `kernels`, `models`, `likelihoods`.

## `velnora.contrib.gp.kernels`

The module exposes `RBF`, `Exponential`, `RationalQuadratic`, `Matern32`, `Matern52`, `Cosine`, `Periodic`, `Linear`, `Polynomial`, `Brownian`, `Constant`, `WhiteNoise`, `Coregionalize`, `Sum`, `Product`, `Exponent`, `VerticalScaling`, `Warping`.

## `velnora.contrib.gp.models`

The module exposes `GPRegression`, `SparseGPRegression`, `VariationalGP`, `VariationalSparseGP`, `GPLVM`.

## `velnora.contrib.gp.likelihoods`

The module exposes `Gaussian`, `Binary`, `MultiClass`, `Poisson`.

## `velnora.contrib.timeseries`

The module exposes `IndependentMaternGP`, `LinearlyCoupledMaternGP`, `DependentMaternGP`, `GenericLGSSM`, `GenericLGSSMWithGPNoiseModel`.

## `velnora.contrib.mue.dataloaders`

The module exposes `BiosequenceDataset`, `write`.

## `velnora.contrib.mue.models`

The module exposes `ProfileHMM`, `FactorMuE`.

## `velnora.contrib.mue.missingdatahmm`

The module exposes `MissingDataDiscreteHMM`.

## `velnora.contrib.mue.statearrangers`

The module exposes `Profile`.

## `velnora.contrib.oed.eig`

The module exposes `nmc_eig`, `posterior_eig`, `marginal_eig`, `marginal_likelihood_eig`, `vnmc_eig`, `lfire_eig`, `donsker_varadhan_eig`.

## `velnora.contrib.tracking.dynamic_models`

The module exposes `NcpContinuous`, `NcpDiscrete`, `NcvContinuous`, `NcvDiscrete`.

## `velnora.contrib.tracking.extended_kalman_filter`

The module exposes `EKFState`.

## `velnora.contrib.tracking.measurements`

The module exposes `PositionMeasurement`.

## `velnora.contrib.tracking.assignment`

The module exposes `MarginalAssignment`, `MarginalAssignmentPersistent`, `MarginalAssignmentSparse`.

## `velnora.distributions.constraints.positive`

Constraint objects are exposed as `real`, `positive`, `simplex`, `positive_definite`, `lower_cholesky`, `ordered_vector` and `corr_matrix`; `interval(lower_bound, upper_bound)` constructs a bounded constraint. `check(value)` returns a boolean tensor over batch members.

## `velnora.distributions.constraints.real`

Constraint objects are exposed as `real`, `positive`, `simplex`, `positive_definite`, `lower_cholesky`, `ordered_vector` and `corr_matrix`; `interval(lower_bound, upper_bound)` constructs a bounded constraint. `check(value)` returns a boolean tensor over batch members.

## `velnora.contrib.cevae.Model`

The object exposed by `CEVAE.model` is callable with `(x, t, y)` and exposes `z_dist()`, `x_dist(z)`, `t_dist(z)` and `y_dist(t, z)`. Each entry returns a distribution object with tensor parameters and `log_prob` and `mean`. Vector distributions expose `base_dist` and `event_shape`.

## `velnora.contrib.cevae.Guide`

The object exposed by `CEVAE.guide` is callable with `(x, t, y)` and exposes `t_dist(x)`, `y_dist(t, x)` and `z_dist(y, t, x)`. Each entry returns a distribution object with tensor parameters and `log_prob` and `mean`. Vector distributions expose `base_dist` and `event_shape`.

## `velnora.distributions.constraints.corr_matrix`

Constraint objects are exposed as `real`, `positive`, `simplex`, `positive_definite`, `lower_cholesky`, `ordered_vector` and `corr_matrix`; `interval(lower_bound, upper_bound)` constructs a bounded constraint. `check(value)` returns a boolean tensor over batch members.

## `velnora.distributions.constraints.lower_cholesky`

Constraint objects are exposed as `real`, `positive`, `simplex`, `positive_definite`, `lower_cholesky`, `ordered_vector` and `corr_matrix`; `interval(lower_bound, upper_bound)` constructs a bounded constraint. `check(value)` returns a boolean tensor over batch members.

## `velnora.distributions.constraints.ordered_vector`

Constraint objects are exposed as `real`, `positive`, `simplex`, `positive_definite`, `lower_cholesky`, `ordered_vector` and `corr_matrix`; `interval(lower_bound, upper_bound)` constructs a bounded constraint. `check(value)` returns a boolean tensor over batch members.

## `velnora.distributions.constraints.positive_definite`

Constraint objects are exposed as `real`, `positive`, `simplex`, `positive_definite`, `lower_cholesky`, `ordered_vector` and `corr_matrix`; `interval(lower_bound, upper_bound)` constructs a bounded constraint. `check(value)` returns a boolean tensor over batch members.

## `velnora.distributions.constraints.simplex`

Constraint objects are exposed as `real`, `positive`, `simplex`, `positive_definite`, `lower_cholesky`, `ordered_vector` and `corr_matrix`; `interval(lower_bound, upper_bound)` constructs a bounded constraint. `check(value)` returns a boolean tensor over batch members.

## `velnora.distributions.transforms.Polynomial`

`Polynomial(autoregressive_nn, input_dim, count_degree, count_sum)` returns a trainable tensor transform exposing `parameters()`, tensor invocation, `inv(value)` and `log_abs_det_jacobian(x, y)`. The three dimension arguments are integers. `autoregressive_nn` is a caller-supplied tensor module accepting `Tensor[..., input_dim]` and returning `Tensor[..., count_sum * (count_degree + 1), input_dim]`. Its middle axis is a flattened pair of term index followed by ascending coefficient-degree index. Forward and inverse results have the input tensor shape; volume results have the leading batch shape.
