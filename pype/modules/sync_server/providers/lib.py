from enum import Enum
from .gdrive import GDriveHandler


class Providers(Enum):
    LOCAL = 'studio'
    GDRIVE = 'gdrive'


class ProviderFactory:
    """
        Factory class as a creator of multiple cloud destination.
        Each new implementation needs to be registered and added to Providers
        enum.
    """
    def __init__(self):
        self.providers = {}  # {'PROVIDER_LABEL: {cls, int},..}

    def register_provider(self, provider, creator, batch_limit):
        """
            Provide all necessary information for one specific remote provider
        Args:
            provider (string): name of provider
            creator (class): class implementing AbstractProvider
            batch_limit (int): number of files that could be processed in
                                    one loop (based on provider API quota)
        Returns:
            modifies self.providers and self.sites
        """
        self.providers[provider] = (creator, batch_limit)

    def get_provider(self, provider, site_name, tree=None):
        """
            Returns new instance of provider client for specific site.
            One provider could have multiple sites.

            'tree' is used for injecting already created memory structure,
            without it constructor of provider would need to calculate it
            from scratch, which could be expensive.
        Args:
            provider (string):  'gdrive','S3'
            site_name (string): descriptor of site, different service accounts
                must have different site name
            tree (dictionary):  - folder paths to folder id structure
        Returns:
            (implementation of AbstractProvider)
        """
        creator_info = self._get_creator_info(provider)
        site = creator_info[0](site_name, tree)  # call init

        return site

    def get_provider_batch_limit(self, provider):
        """
            Each provider has some limit of files that could be  processed in
            one batch (loop step). It is not 'file' limit per se, but
            calculation based on API queries for provider.
            (For example 'gdrive' has 1000 queries for 100 sec, one file could
            be multiple queries (one for each level of path + check if file
            exists)
        Args:
            provider (string): 'gdrive','S3'
        Returns:
        """
        info = self._get_creator_info(provider)
        return info[1]

    def _get_creator_info(self, provider):
        """
            Collect all necessary info for provider. Currently only creator
            class and batch limit
        Args:
            provider (string): 'gdrive' etc
        Returns:
        """
        creator_info = self.providers.get(provider)
        if not creator_info:
            raise ValueError(
                "Provider {} not registered yet".format(provider))
        return creator_info


factory = ProviderFactory()
factory.register_provider('gdrive', GDriveHandler, 7)
