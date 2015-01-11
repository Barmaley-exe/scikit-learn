"""
Linear Discriminant Analysis (LDA)
"""

# Authors: Clemens Brunner
#          Martin Billinger
#          Matthieu Perrot
#          Mathieu Blondel

# License: BSD 3-Clause

from __future__ import print_function
import warnings

import numpy as np
from scipy import linalg
from six import string_types

from .base import BaseEstimator, TransformerMixin
from .linear_model.base import LinearClassifierMixin
from .covariance import ledoit_wolf, empirical_covariance, shrunk_covariance
from .utils.multiclass import unique_labels
from .utils import check_array, check_X_y
from .preprocessing import StandardScaler


__all__ = ['LDA']


def _cov(X, shrinkage=None):
    """Estimate covariance matrix (using optional shrinkage).

    Parameters
    ----------
    X : array-like, shape (n_samples, n_features)
        Input data.

    shrinkage : string or float, optional
        Shrinkage parameter, possible values:
          - None or 'empirical': no shrinkage (default).
          - 'auto': automatic shrinkage using the Ledoit-Wolf lemma.
          - float between 0 and 1: fixed shrinkage parameter.

    Returns
    -------
    s : array, shape (n_features, n_features)
        Estimated covariance matrix.
    """
    shrinkage = "empirical" if shrinkage is None else shrinkage
    if isinstance(shrinkage, string_types):
        if shrinkage == 'auto':
            sc = StandardScaler()  # standardize features
            X = sc.fit_transform(X)
            s = sc.std_ * ledoit_wolf(X)[0] * sc.std_  # scale back
        elif shrinkage == 'empirical':
            s = empirical_covariance(X)
        else:
            raise ValueError('unknown shrinkage parameter')
    elif isinstance(shrinkage, float) or isinstance(shrinkage, int):
        if shrinkage < 0 or shrinkage > 1:
            raise ValueError('shrinkage parameter must be between 0 and 1')
        s = shrunk_covariance(empirical_covariance(X), shrinkage)
    else:
        raise TypeError('shrinkage must be of string or int type')
    return s


def _class_means(X, y):
    """Compute class means.

    Parameters
    ----------
    X : array-like, shape (n_samples, n_features)
        Input data.

    y : array-like, shape (n_samples,) or (n_samples, n_targets)
        Target values.

    Returns
    -------
    means : array-like, shape (n_features,)
        Class means.
    """
    means = []
    classes = np.unique(y)
    for group in classes:
        Xg = X[y == group, :]
        means.append(Xg.mean(0))
    return np.asarray(means)


def _class_cov(X, y, priors=None, shrinkage=None):
    """Compute class covariance matrix.

    Parameters
    ----------
    X : array-like, shape (n_samples, n_features)
        Input data.

    y : array-like, shape (n_samples,) or (n_samples, n_targets)
        Target values.

    priors : array-like, shape (n_classes,)
        Class priors.

    shrinkage : string or float, optional
        Shrinkage parameter, possible values:
          - None: no shrinkage (default).
          - 'auto': automatic shrinkage using the Ledoit-Wolf lemma.
          - float between 0 and 1: fixed shrinkage parameter.

    Returns
    -------
    cov : array-like, shape (n_features, n_features)
        Class covariance matrix.
    """
    classes = np.unique(y)
    covs = []
    for group in classes:
        Xg = X[y == group, :]
        covs.append(np.atleast_2d(_cov(Xg, shrinkage)))
    return np.average(covs, axis=0, weights=priors)


class LDA(BaseEstimator, LinearClassifierMixin, TransformerMixin):
    """Linear Discriminant Analysis (LDA).

    A classifier with a linear decision boundary, generated by fitting class
    conditional densities to the data and using Bayes' rule.

    The model fits a Gaussian density to each class, assuming that all classes
    share the same covariance matrix.

    The fitted model can also be used to reduce the dimensionality of the input
    by projecting it to the most discriminative directions.

    Parameters
    ----------
    solver : string, optional
        Solver to use, possible values:
          - 'svd': Singular value decomposition (default). Does not compute the
                covariance matrix, therefore this solver is recommended for
                data with a large number of features.
          - 'lsqr': Least squares solution, can be combined with shrinkage.
          - 'eigen': Eigenvalue decomposition, can be combined with shrinkage.

    shrinkage : string or float, optional
        Shrinkage parameter, possible values:
          - None: no shrinkage (default).
          - 'auto': automatic shrinkage using the Ledoit-Wolf lemma.
          - float between 0 and 1: fixed shrinkage parameter.
        Note that shrinkage works only with 'lsqr' and 'eigen' solvers.

    priors : array, optional, shape (n_classes,)
        Class priors.

    n_components : int, optional
        Number of components (< n_classes - 1) for dimensionality reduction.

    Attributes
    ----------
    coef_ : array, shape (n_features,) or (n_classes, n_features)
        Weight vector(s).

    intercept_ : array, shape (n_features,)
        Intercept term.

    covariance_ : array-like, shape (n_features, n_features)
        Covariance matrix (shared by all classes).

    means_ : array-like, shape (n_classes, n_features)
        Class means.

    priors_ : array-like, shape (n_classes,)
        Class priors (sum to 1).

    scalings_ : array-like, shape (rank, n_classes - 1)
        Scaling of the features in the space spanned by the class centroids.

    xbar_ : array-like, shape (n_features,)
        Overall mean.

    classes_ : array-like, shape (n_classes,)
        Unique class labels.

    See also
    --------
    sklearn.qda.QDA: Quadratic discriminant analysis

    Notes
    -----
    The default solver is 'svd'. It can perform both classification and
    transform, and it does not rely on the calculation of the covariance
    matrix. This can be an advantage in situations where the number of features
    is large. However, the 'svd' solver cannot be used with shrinkage.

    The 'lsqr' solver is an efficient algorithm that only works for
    classification. It supports shrinkage.

    The 'eigen' solver is based on the optimization of the between class
    scatter to within class scatter ratio. It can be used for both
    classification and transform, and it supports shrinkage. However, the
    'eigen' solver needs to compute the covariance matrix, so it might not be
    suitable for situations with a high number of features.

    Examples
    --------
    >>> import numpy as np
    >>> from sklearn.lda import LDA
    >>> X = np.array([[-1, -1], [-2, -1], [-3, -2], [1, 1], [2, 1], [3, 2]])
    >>> y = np.array([1, 1, 1, 2, 2, 2])
    >>> clf = LDA()
    >>> clf.fit(X, y)
    LDA(n_components=None, priors=None, shrinkage=None, solver='svd',
      store_covariance=False, tol=0.0001)
    >>> print(clf.predict([[-0.8, -1]]))
    [1]
    """
    def __init__(self, solver='svd', shrinkage=None, priors=None,
                 n_components=None, store_covariance=False, tol=1e-4):
        self.solver = solver
        self.shrinkage = shrinkage
        self.priors = priors
        self.n_components = n_components
        self.store_covariance = store_covariance  # used only in svd solver
        self.tol = tol  # used only in svd solver

    def _solve_lsqr(self, X, y, shrinkage):
        """Least squares solver.

        The least squares solver computes a straightforward solution of the
        optimal decision rule based directly on the discriminant functions. It
        can only be used for classification (with optional shrinkage), because
        estimation of eigenvectors is not performed. Therefore, dimensionality
        reduction with the transform is not supported.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            Training data.

        y : array-like, shape (n_samples,) or (n_samples, n_classes)
            Target values.

        shrinkage : string or float, optional
            Shrinkage parameter, possible values:
              - None: no shrinkage (default).
              - 'auto': automatic shrinkage using the Ledoit-Wolf lemma.
              - float between 0 and 1: fixed shrinkage parameter.

        Notes
        -----
        This solver is based on [1]_, section 2.6.2, pp. 39-41.

        References
        ----------
        .. [1] R. O. Duda, P. E. Hart, D. G. Stork. Pattern Classification
           (Second Edition). John Wiley & Sons, Inc., New York, 2001. ISBN
           0-471-05669-3.
        """
        self.means_ = _class_means(X, y)
        self.covariance_ = _class_cov(X, y, self.priors_, shrinkage)
        self.coef_ = linalg.lstsq(self.covariance_, self.means_.T)[0].T
        self.intercept_ = (-0.5 * np.diag(np.dot(self.means_, self.coef_.T))
                           + np.log(self.priors_))

    def _solve_eigen(self, X, y, shrinkage):
        """Eigenvalue solver.

        The eigenvalue solver computes the optimal solution of the Rayleigh
        coefficient (basically the ratio of between class scatter to within
        class scatter). This solver supports both classification and
        dimensionality reduction (with optional shrinkage).

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            Training data.

        y : array-like, shape (n_samples,) or (n_samples, n_targets)
            Target values.

        shrinkage : string or float, optional
            Shrinkage parameter, possible values:
              - None: no shrinkage (default).
              - 'auto': automatic shrinkage using the Ledoit-Wolf lemma.
              - float between 0 and 1: fixed shrinkage constant.

        Notes
        -----
        This solver is based on [1]_, section 3.8.3, pp. 121-124.

        References
        ----------
        .. [1] R. O. Duda, P. E. Hart, D. G. Stork. Pattern Classification
           (Second Edition). John Wiley & Sons, Inc., New York, 2001. ISBN
           0-471-05669-3.
        """
        self.means_ = _class_means(X, y)
        self.covariance_ = _class_cov(X, y, self.priors_, shrinkage)

        Sw = self.covariance_  # within scatter
        St = _cov(X, shrinkage)  # total scatter
        Sb = St - Sw  # between scatter

        evals, evecs = linalg.eigh(Sb, Sw)
        evecs = evecs[:, np.argsort(evals)[::-1]]  # sort eigenvectors
        # evecs /= np.linalg.norm(evecs, axis=0)  # doesn't work with numpy 1.6
        evecs /= np.apply_along_axis(np.linalg.norm, 0, evecs)

        self.scalings_ = evecs
        self.coef_ = np.dot(self.means_, evecs).dot(evecs.T)
        self.intercept_ = (-0.5 * np.diag(np.dot(self.means_, self.coef_.T))
                           + np.log(self.priors_))

    def _solve_svd(self, X, y, store_covariance=False, tol=1.0e-4):
        """SVD solver.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            Training data.

        y : array-like, shape (n_samples,) or (n_samples, n_targets)
            Target values.

        store_covariance : bool, optional
            Additionally compute class covariance matrix (default False).

        tol : float, optional
            Threshold used for rank estimation.
        """
        n_samples, n_features = X.shape
        n_classes = len(self.classes_)

        self.means_ = _class_means(X, y)
        if store_covariance:
            self.covariance_ = _class_cov(X, y, self.priors_)

        Xc = []
        for idx, group in enumerate(self.classes_):
            Xg = X[y == group, :]
            Xc.append(Xg - self.means_[idx])

        self.xbar_ = np.dot(self.priors_, self.means_)

        Xc = np.concatenate(Xc, axis=0)

        # 1) within (univariate) scaling by with classes std-dev
        std = Xc.std(axis=0)
        # avoid division by zero in normalization
        std[std == 0] = 1.
        fac = 1. / (n_samples - n_classes)

        # 2) Within variance scaling
        X = np.sqrt(fac) * (Xc / std)
        # SVD of centered (within)scaled data
        U, S, V = linalg.svd(X, full_matrices=False)

        rank = np.sum(S > tol)
        if rank < n_features:
            warnings.warn("Variables are collinear.")
        # Scaling of within covariance is: V' 1/S
        scalings = (V[:rank] / std).T / S[:rank]

        # 3) Between variance scaling
        # Scale weighted centers
        X = np.dot(((np.sqrt((n_samples * self.priors_) * fac)) *
                    (self.means_ - self.xbar_).T).T, scalings)
        # Centers are living in a space with n_classes-1 dim (maximum)
        # Use SVD to find projection in the space spanned by the
        # (n_classes) centers
        _, S, V = linalg.svd(X, full_matrices=0)

        rank = np.sum(S > tol * S[0])
        self.scalings_ = np.dot(scalings, V.T[:, :rank])
        coef = np.dot(self.means_ - self.xbar_, self.scalings_)
        self.intercept_ = (-0.5 * np.sum(coef**2, axis=1)
                           + np.log(self.priors_))
        self.coef_ = np.dot(coef, self.scalings_.T)
        self.intercept_ -= np.dot(self.xbar_, self.coef_.T)

    def fit(self, X, y, store_covariance=False, tol=1.0e-4):
        """Fit LDA model according to the given training data and parameters.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            Training data.

        y : array, shape (n_samples,)
            Target values.
        """
        if store_covariance:
            warnings.warn("'store_covariance' was moved to the __init__()"
                          "method in version 0.16 and will be removed from"
                          "fit() in version 0.18.", DeprecationWarning)
        else:
            store_covariance = self.store_covariance
        if tol != 1.0e-4:
            warnings.warn("'tol' was moved to __init__() method in version"
                          " 0.16 and will be removed from fit() in 0.18",
                          DeprecationWarning)
            self.tol = tol
        X, y = check_X_y(X, y)
        self.classes_ = unique_labels(y)

        if self.priors is None:  # estimate priors from sample
            _, y_t = np.unique(y, return_inverse=True)  # non-negative ints
            self.priors_ = np.bincount(y_t) / float(len(y))
        else:
            self.priors_ = self.priors

        if self.solver == 'svd':
            if self.shrinkage is not None:
                raise NotImplementedError('shrinkage not supported')
            self._solve_svd(X, y, store_covariance=store_covariance, tol=tol)
        elif self.solver == 'lsqr':
            self._solve_lsqr(X, y, shrinkage=self.shrinkage)
        elif self.solver == 'eigen':
            self._solve_eigen(X, y, shrinkage=self.shrinkage)
        else:
            raise ValueError("unknown solver {} (valid solvers are 'svd', "
                             "'lsqr', and 'eigen').".format(self.solver))
        if self.classes_.size == 2:  # treat binary case as a special case
            self.coef_ = np.array(self.coef_[1, :] - self.coef_[0, :], ndmin=2)
            self.intercept_ = np.array(self.intercept_[1] - self.intercept_[0],
                                       ndmin=1)
        return self

    def transform(self, X):
        """Project data to maximize class separation.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            Input data.

        Returns
        -------
        X_new : array, shape (n_samples, n_components)
            Transformed data.
        """
        X = check_array(X)
        if self.solver == 'lsqr':
            raise NotImplementedError("transform not implemented for 'lsqr' "
                                      "solver (use 'svd' or 'eigen').")
        elif self.solver == 'svd':
            X_new = np.dot(X - self.xbar_, self.scalings_)
        elif self.solver == 'eigen':
            X_new = np.dot(X, self.scalings_)
        n_components = X.shape[1] if self.n_components is None \
            else self.n_components
        return X_new[:, :n_components]

    def predict_proba(self, X):
        """Estimate probability.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            Input data.

        Returns
        -------
        C : array, shape (n_samples, n_classes)
            Estimated probabilities.
        """
        prob = self.decision_function(X)
        prob *= -1
        np.exp(prob, prob)
        prob += 1
        np.reciprocal(prob, prob)
        if len(self.classes_) == 2:  # binary case
            return np.column_stack([1 - prob, prob])
        else:
            # OvR normalization, like LibLinear's predict_probability
            prob /= prob.sum(axis=1).reshape((prob.shape[0], -1))
            return prob

    def predict_log_proba(self, X):
        """Estimate log probability.

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            Input data.

        Returns
        -------
        C : array, shape (n_samples, n_classes)
            Estimated log probabilities.
        """
        return np.log(self.predict_proba(X))
