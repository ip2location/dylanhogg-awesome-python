import time
from datetime import datetime, timedelta
from tenacity import retry, wait_exponential, stop_after_attempt
from loguru import logger
from library.ghw import GithubWrapper
from joblib import Memory
from github import PaginatedList
from github.GithubException import RateLimitExceededException, GithubException

memory = Memory(".joblib_cache")


def log_retry(state):
    msg = (
        f"Tenacity retry {state.fn.__name__}: {state.attempt_number=}, {state.idle_for=}, {state.seconds_since_start=}"
    )
    if state.attempt_number < 1:
        logger.info(msg)
    else:
        logger.exception(msg)


class StandardMetrics:
    @staticmethod
    @memory.cache(ignore=["ghw"])
    @retry(wait=wait_exponential(multiplier=2, min=10, max=1200), stop=stop_after_attempt(50), before_sleep=log_retry)
    def get_repo_topics(ghw: GithubWrapper, name: str):
        topics = ghw.get_repo(name).get_topics()  # TODO: investigate ordering (influences topN in UI)
        # Remove generic topics
        remove_topics = ["python", "python2", "python-2", "python3", "python-3",
                         "python-library", "library", "pypi-package", "pypi"]
        for t in remove_topics:
            if t in topics:
                topics.remove(t)
        return topics

    @staticmethod
    def join_topics(custom_topics: list, github_topics: list) -> list:
        # Remove duplicates from a list, while preserving order
        # https://stackoverflow.com/questions/480214/how-do-i-remove-duplicates-from-a-list-while-preserving-order/17016257#17016257
        return list(dict.fromkeys(custom_topics + github_topics))

    @staticmethod
    @memory.cache(ignore=["ghw"])
    @retry(wait=wait_exponential(multiplier=2, min=10, max=1200), stop=stop_after_attempt(50), before_sleep=log_retry)
    def last_commit_date(ghw: GithubWrapper, name: str):
        modified = ghw.get_repo(name).get_commits().get_page(0)[0].last_modified
        return datetime.strptime(
            modified,
            "%a, %d %b %Y %H:%M:%S %Z",
        ).date()

    @staticmethod
    def get_display_description(row):
        if row["_github_description"] is not None:
            return row["_github_description"]
        elif row["customabout"] is not None:
            return row["customabout"]
        else:
            assert row["_organization"] is not None
            assert row["_reponame"] is not None
            return f'{row["_organization"]}/{row["_reponame"]}'

        # TEMP: Old version before customabout introduced:
        # repo = ghw.get_repo(name)
        # if repo.description is None:
        #     return f"{name}"
        # else:
        #     assert repo.name is not None
        #     if (
        #         repo.description.lower().startswith(repo.name.lower())
        #         or f"{repo.name.lower()}:" in repo.description.lower()
        #     ):
        #         return f"{repo.description}"
        #     else:
        #         return f"{repo.name}: {repo.description}"


class PopularityMetrics:
    """
    Inspired by https://github.com/ossf/criticality_score/tree/v1.0.7 (Latest Python version before Go port)
    and https://github.com/ossf/criticality_score/blob/main/Quantifying_criticality_algorithm.pdf
    """

    @staticmethod
    @memory.cache(ignore=["ghw"])
    @retry(wait=wait_exponential(multiplier=2, min=10, max=1200), stop=stop_after_attempt(50), before_sleep=log_retry)
    def _get_contributors(ghw: GithubWrapper, name: str, anon: str = "true") -> PaginatedList:
        repo = ghw.get_repo(name)
        return repo.get_contributors(anon=anon)

    @staticmethod
    @memory.cache(ignore=["ghw"])
    @retry(wait=wait_exponential(multiplier=2, min=10, max=1200), stop=stop_after_attempt(50), before_sleep=log_retry)
    def contributor_count(ghw: GithubWrapper, name: str) -> int:
        try:
            return PopularityMetrics._get_contributors(ghw, name).totalCount
        except RateLimitExceededException as ex:
            logger.error(f"contributor_count rate exception: {ex}")
            raise ex
        except Exception as ex:
            # Typically a large number of contributors
            logger.warning(f"contributor_count exception: {ex}")
            return 5000

    # @staticmethod
    # @memory.cache
    # def _get_contributor_company(contributor):
    #     return contributor.company

    @staticmethod
    @memory.cache(ignore=["ghw"])
    @retry(wait=wait_exponential(multiplier=2, min=10, max=1200), stop=stop_after_attempt(50), before_sleep=log_retry)
    def contributor_orgs_dict(ghw: GithubWrapper, name: str, sleep: int = 1, max_contrib_count: int = 10) -> dict:
        repo = ghw.get_repo(name)  # TODO: randomise token_list in ghw??

        def _filter_name(org_name):
            return (
                org_name.lower()
                .replace(" ", "")
                .replace(",inc.", "")
                .replace("inc.", "")
                .replace("llc", "")
                .replace("@", "")
                .rstrip(",")
            )

        contributor_logins = set()
        orgs = set()
        orgs_raw = set()
        contributors = repo.get_contributors()[:max_contrib_count]
        try:
            # NOTE: Can be expensive if not capped due to `contributor.company` being an API call
            logger.info(f"contributor_orgs_dict {contributors=}")
            for i, contributor in enumerate(contributors):
                # contributor_company = PopularityMetrics._get_contributor_company(contributor)  # TODO: review need to cache here
                contributor_company = contributor.company
                time.sleep(sleep)
                if contributor_company:
                    filtered_contributor_company = _filter_name(contributor_company)
                    logger.info(
                        f"{i}. Company hit : {name=}, {contributor.login=}, "
                        f"{contributor_company=}, {filtered_contributor_company=}"
                    )
                    orgs_raw.add(contributor_company)
                    orgs.add(filtered_contributor_company)
                    contributor_logins.add(f"{contributor.login}@{filtered_contributor_company}")
                else:
                    logger.info(f"{i}. Company miss: {name=}, {contributor.login=}")
                    contributor_logins.add(contributor.login)
        except RateLimitExceededException as ex:
            logger.warning(f"get_contributor_company rate exception ({sleep=}): {ex}")
            raise ex
        except Exception as ex:
            # Typically a large number of contributors
            logger.warning(f"get_contributor_company {type(ex)} exception: {ex}")
            return {
                # "_pop_contributor_logins": None,
                "_pop_contributor_orgs_len": -1,
                # "_pop_contributor_orgs_max": max_contrib_count,
                # "_pop_contributor_orgs": None,
                # "_pop_contributor_orgs_raw": None,
                "_pop_contributor_orgs_error": len(str(ex))
                # "_pop_contributor_orgs_error": str(ex)
            }
        return {
            # "_pop_contributor_logins": sorted(contributor_logins),
            "_pop_contributor_orgs_len": len(orgs),
            # "_pop_contributor_orgs_max": max_contrib_count,
            # "_pop_contributor_orgs": sorted(orgs),
            # "_pop_contributor_orgs_raw": sorted(orgs_raw),
            # "_pop_contributor_orgs_error": None
        }

    @staticmethod
    @memory.cache(ignore=["ghw"])
    @retry(wait=wait_exponential(multiplier=2, min=10, max=1200), stop=stop_after_attempt(50), before_sleep=log_retry)
    def commit_frequency(ghw: GithubWrapper, name: str) -> float:
        repo = ghw.get_repo(name)
        # NOTE: get_stats_commit_activity Returns the last year of commit activity grouped by week
        stats_commit_activity = repo.get_stats_commit_activity()
        if not stats_commit_activity:
            # NOTE: have only seen stats_commit_activity=None for the-algorithm-ml/issues which has 1 commit.
            logger.warning(f"stats_commit_activity was None for {name=}")
            return 1
        assert len(stats_commit_activity) == 52, f"len(stats_commit_activity) was not 52 as expected"
        total = 0
        for week_stat in stats_commit_activity:
            total += week_stat.total
        return round(total / len(stats_commit_activity), 2)

    @staticmethod
    @memory.cache(ignore=["ghw"])
    @retry(wait=wait_exponential(multiplier=2, min=10, max=1200), stop=stop_after_attempt(50), before_sleep=log_retry)
    def updated_issues_count(ghw: GithubWrapper, name: str) -> int:
        ISSUE_LOOKBACK_DAYS = 90
        repo = ghw.get_repo(name)
        issues_since_time = datetime.utcnow() - timedelta(days=ISSUE_LOOKBACK_DAYS)
        # NOTE: get_issues includes PR's
        return repo.get_issues(state="all", since=issues_since_time).totalCount

    @staticmethod
    @memory.cache(ignore=["ghw"])
    @retry(wait=wait_exponential(multiplier=2, min=10, max=1200), stop=stop_after_attempt(50), before_sleep=log_retry)
    def closed_issues_count(ghw: GithubWrapper, name: str) -> int:
        ISSUE_LOOKBACK_DAYS = 90
        # TODO: make generic with updated_issues_count?
        repo = ghw.get_repo(name)
        issues_since_time = datetime.utcnow() - timedelta(days=ISSUE_LOOKBACK_DAYS)
        # NOTE: get_issues includes PR's
        return repo.get_issues(state="closed", since=issues_since_time).totalCount

    @staticmethod
    @memory.cache(ignore=["ghw"])
    @retry(wait=wait_exponential(multiplier=2, min=10, max=1200), stop=stop_after_attempt(50), before_sleep=log_retry)
    def created_since_days(ghw: GithubWrapper, name: str) -> int:
        repo = ghw.get_repo(name)
        creation_time = repo.created_at

        # See if there exist any commits before this repository creation
        # time on GitHub. If yes, then the repository creation time is not
        # correct, and it was residing somewhere else before. So, use the first
        # commit date.
        # TODO: commented out as not using the result for anything yet
        #       should look into this more
        # prior_creation_commit_count = repo.get_commits(until=creation_time).totalCount
        # if prior_creation_commit_count:
        #     logger.warning(
        #         f"{name} has {prior_creation_commit_count=}, repository creation time is not correct, "
        #         f"and it was residing somewhere else before"
        #     )
        #     # TODO: see how often this happens
        #     # first_commit_time = self.get_first_commit_time()
        #     # if first_commit_time:
        #     #     creation_time = min(creation_time, first_commit_time)

        difference = datetime.utcnow() - creation_time
        return round(difference.days / 30)

    @staticmethod
    @memory.cache(ignore=["ghw"])
    @retry(wait=wait_exponential(multiplier=2, min=10, max=1200), stop=stop_after_attempt(50), before_sleep=log_retry)
    def updated_since_days(ghw: GithubWrapper, name: str) -> int:
        repo = ghw.get_repo(name)
        last_commit = repo.get_commits()[0]
        last_commit_time = last_commit.commit.author.date
        difference = datetime.utcnow() - last_commit_time
        return round(difference.days / 30)

    @staticmethod
    @memory.cache(ignore=["ghw"])
    @retry(wait=wait_exponential(multiplier=2, min=10, max=1200), stop=stop_after_attempt(50), before_sleep=log_retry)
    def recent_releases_count_dict(ghw: GithubWrapper, name: str) -> dict:
        RELEASE_LOOKBACK_DAYS = 365
        repo = ghw.get_repo(name)
        recent_releases_count = 0
        for release in repo.get_releases():
            if (datetime.utcnow() - release.created_at).days > RELEASE_LOOKBACK_DAYS:
                continue
            recent_releases_count += 1

        estimated_tags = 0
        # Make rough estimation of tags used in last year from overall
        # project history. This query is extremely expensive, so instead
        # do the rough calculation.
        days_since_creation = PopularityMetrics.created_since_days(ghw, name) * 30
        if days_since_creation:
            try:
                total_tags = repo.get_tags().totalCount
            except KeyError as ex:
                # 2013-04-05: Saw this error on repo.get_tags().totalCount a few times with 'giswqs/leafmap':
                # File "/Users/dylan/_gitdrh/crazy-awesome-python/venv/lib/python3.9/site-packages/
                #       github/PaginatedList.py", line 163, in totalCount
                #     self.__totalCount = int(parse_qs(lastUrl)["page"][0])
                # KeyError: 'page'
                total_tags = 1
                logger.error(f"recent_releases_count_dict KeyError for {name=}: {ex}")
                logger.error(f"This could be due to a repo org move like giswqs/leafmap -> opengeos/leafmap")
                raise ex
            estimated_tags = round((total_tags / days_since_creation) * RELEASE_LOOKBACK_DAYS)

        recent_releases_adjusted_count = recent_releases_count
        if not recent_releases_count:
            recent_releases_adjusted_count = estimated_tags

        return {
            "_pop_recent_releases_count": recent_releases_count,
            "_pop_recent_releases_estimated_tags": estimated_tags,
            "_pop_recent_releases_adjusted_count": recent_releases_adjusted_count,  # TODO: review need and name
        }

    @staticmethod
    @memory.cache(ignore=["ghw"])
    # @retry(wait=wait_exponential(multiplier=2, min=10, max=1200), stop=stop_after_attempt(50), before_sleep=log_retry)
    def comment_frequency(ghw: GithubWrapper, name: str) -> dict:
        ISSUE_LOOKBACK_DAYS = 90
        repo = ghw.get_repo(name)
        issues_since_time = datetime.utcnow() - timedelta(days=ISSUE_LOOKBACK_DAYS)
        # NOTE: get_issues includes PR's
        issue_count = repo.get_issues(state="all", since=issues_since_time).totalCount

        try:
            comment_count = repo.get_issues_comments(since=issues_since_time).totalCount
        except GithubException as ex:
            logger.warning(f"get_issues_comments exception: {ex}, will retry...")
            time.sleep(5)
            # Exception due to large number of comments, e.g. pytorch/pytorch repo.
            # So try reducing down ISSUE_LOOKBACK_DAYS
            ISSUE_LOOKBACK_DAYS = ISSUE_LOOKBACK_DAYS // 4
            issues_since_time = datetime.utcnow() - timedelta(days=ISSUE_LOOKBACK_DAYS)
            comment_count = repo.get_issues_comments(since=issues_since_time).totalCount * 4

        comment_frequency = round(comment_count / issue_count, 1) if issue_count else 0

        return {
            "_pop_issue_count": issue_count,
            "_pop_comment_count": comment_count,
            "_pop_comment_count_lookback_days": ISSUE_LOOKBACK_DAYS,
            "_pop_comment_frequency": comment_frequency,
        }
