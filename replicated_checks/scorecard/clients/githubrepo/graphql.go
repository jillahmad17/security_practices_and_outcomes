// Copyright 2021 OpenSSF Scorecard Authors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package githubrepo

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/shurcooL/githubv4"

	_ "github.com/duckdb/duckdb-go/v2"

	"github.com/ossf/scorecard/v5/clients"
	sce "github.com/ossf/scorecard/v5/errors"
)

const (
	pullRequestsToAnalyze  = 1
	checksToAnalyze        = 30
	issuesToAnalyze        = 30
	issueCommentsToAnalyze = 30
	reviewsToAnalyze       = 30
	labelsToAnalyze        = 30

	// https://docs.github.com/en/graphql/overview/rate-limits-and-node-limits-for-the-graphql-api#node-limit
	defaultPageLimit = 100
	retryLimit       = 3
)

//nolint:govet
type graphqlData struct {
	Repository struct {
		IsArchived githubv4.Boolean
		ArchivedAt githubv4.DateTime
		Object     struct {
			Commit struct {
				History struct {
					Nodes []struct {
						CommittedDate githubv4.DateTime
						Message       githubv4.String
						Oid           githubv4.GitObjectID
						Author        struct {
							User struct {
								Login githubv4.String
							}
						}
						Committer struct {
							Name *string
							User struct {
								Login *string
							}
						}
						Signature struct {
							IsValid           bool
							WasSignedByGitHub bool
						}
						AssociatedPullRequests struct {
							Nodes []struct {
								Repository struct {
									Name  githubv4.String
									Owner struct {
										Login githubv4.String
									}
								}
								Author struct {
									Login        githubv4.String
									ResourcePath githubv4.String
								}
								Number     githubv4.Int
								HeadRefOid githubv4.String
								MergedAt   githubv4.DateTime
								Labels     struct {
									Nodes []struct {
										Name githubv4.String
									}
								} `graphql:"labels(last: $labelsToAnalyze)"`
								Reviews struct {
									Nodes []struct {
										State  githubv4.String
										Author struct {
											Login githubv4.String
										}
									}
								} `graphql:"reviews(last: $reviewsToAnalyze)"`
								MergedBy struct {
									Login githubv4.String
								}
							}
						} `graphql:"associatedPullRequests(first: $pullRequestsToAnalyze)"`
					}
					PageInfo struct {
						StartCursor githubv4.String
						EndCursor   githubv4.String
						HasNextPage bool
					}
				} `graphql:"history(first: $commitsToAnalyze, after: $historyCursor)"`
			} `graphql:"... on Commit"`
		} `graphql:"object(expression: $commitExpression)"`
		Issues struct {
			Nodes []struct {
				//nolint:revive,stylecheck // naming according to githubv4 convention.
				Url               *string
				AuthorAssociation *string
				Author            struct {
					Login githubv4.String
				}
				CreatedAt *time.Time
				Comments  struct {
					Nodes []struct {
						AuthorAssociation *string
						CreatedAt         *time.Time
						Author            struct {
							Login githubv4.String
						}
					}
				} `graphql:"comments(last: $issueCommentsToAnalyze)"`
			}
		} `graphql:"issues(first: $issuesToAnalyze, orderBy:{field:UPDATED_AT, direction:DESC})"`
	} `graphql:"repository(owner: $owner, name: $name)"`
	RateLimit struct {
		Cost *int
	}
}

type graphqlHandler struct {
	client      *githubv4.Client
	data        *graphqlData
	setupOnce   *sync.Once
	ctx         context.Context
	errSetup    error
	repourl     *Repo
	commits     []clients.Commit
	issues      []clients.Issue
	archived    bool
	archivedAt  time.Time
	commitDepth int
}

func (handler *graphqlHandler) init(ctx context.Context, repourl *Repo, commitDepth int) {
	handler.ctx = ctx
	handler.repourl = repourl
	handler.data = new(graphqlData)
	handler.errSetup = nil
	handler.setupOnce = new(sync.Once)
	handler.commitDepth = commitDepth
	handler.commits = nil
	handler.issues = nil
}

func populateCommits(handler *graphqlHandler, vars map[string]interface{}) ([]clients.Commit, error) {
	var commits []clients.Commit
	commitsLeft, ok := vars["commitsToAnalyze"].(githubv4.Int)
	if !ok {
		return nil, sce.WithMessage(sce.ErrScorecardInternal, "unexpected type")
	}
	commitsRequested := min(defaultPageLimit, commitsLeft)
	var retries int
	for commitsLeft > 0 {
		vars["commitsToAnalyze"] = commitsRequested
		if err := handler.client.Query(handler.ctx, handler.data, vars); err != nil {
			// 502 usually indicate timeouts, where we're requesting too much data
			// so make our requests smaller and try again
			if retries < retryLimit && strings.Contains(err.Error(), "502 Bad Gateway") {
				retries++
				commitsRequested /= 2
				continue
			}
			return nil, sce.WithMessage(sce.ErrScorecardInternal, fmt.Sprintf("githubv4.Query: %v", err))
		}
		vars["historyCursor"] = handler.data.Repository.Object.Commit.History.PageInfo.EndCursor
		tmp, err := commitsFrom(handler.data, handler.repourl.owner, handler.repourl.repo)
		if err != nil {
			return nil, fmt.Errorf("failed to populate commits: %w", err)
		}
		commits = append(commits, tmp...)
		commitsLeft -= commitsRequested
		commitsRequested = min(commitsRequested, commitsLeft)
	}
	return commits, nil
}

func (handler *graphqlHandler) setup() error {
	handler.setupOnce.Do(func() {
		commitExpression := handler.repourl.commitExpression()
		vars := map[string]interface{}{
			"owner":                  githubv4.String(handler.repourl.owner),
			"name":                   githubv4.String(handler.repourl.repo),
			"pullRequestsToAnalyze":  githubv4.Int(pullRequestsToAnalyze),
			"issuesToAnalyze":        githubv4.Int(issuesToAnalyze),
			"issueCommentsToAnalyze": githubv4.Int(issueCommentsToAnalyze),
			"reviewsToAnalyze":       githubv4.Int(reviewsToAnalyze),
			"labelsToAnalyze":        githubv4.Int(labelsToAnalyze),
			"commitsToAnalyze":       githubv4.Int(handler.commitDepth),
			"commitExpression":       githubv4.String(commitExpression),
			"historyCursor":          (*githubv4.String)(nil),
		}
		handler.commits, handler.errSetup = populateCommits(handler, vars)

		//heres where we would add get contributors... from a given commit
		handler.issues = issuesFrom(handler.data)

		handler.archived = bool(handler.data.Repository.IsArchived)
		handler.archivedAt = handler.data.Repository.ArchivedAt.Time
	})
	return handler.errSetup
}

func (handler *graphqlHandler) getCommits() ([]clients.Commit, error) {
	if err := handler.setup(); err != nil {
		return nil, fmt.Errorf("error during graphqlHandler.setup: %w", err)
	}
	return handler.commits, nil
}

type WebhookPayload struct {
	Action  string  `json:"action"`
	Issue   Issue   `json:"issue"`
	Comment Comment `json:"comment"`
}

type Issue struct {
	URL           string `json:"url"`
	RepositoryURL string `json:"repository_url"`
	LabelsURL     string `json:"labels_url"`
	CommentsURL   string `json:"comments_url"`
	EventsURL     string `json:"events_url"`
	HTMLURL       string `json:"html_url"`

	ID     int64  `json:"id"`
	NodeID string `json:"node_id"`
	Number int    `json:"number"`
	Title  string `json:"title"`

	User User `json:"user"`

	State     string        `json:"state"`
	Locked    bool          `json:"locked"`
	Assignee  interface{}   `json:"assignee"`
	Assignees []interface{} `json:"assignees"`
	Milestone interface{}   `json:"milestone"`

	Comments  int     `json:"comments"`
	CreatedAt string  `json:"created_at"`
	UpdatedAt string  `json:"updated_at"`
	ClosedAt  *string `json:"closed_at"`

	AuthorAssociation string  `json:"author_association"`
	ActiveLockReason  *string `json:"active_lock_reason"`

	Body string `json:"body"`

	Reactions Reactions `json:"reactions"`

	TimelineURL           string      `json:"timeline_url"`
	PerformedViaGithubApp interface{} `json:"performed_via_github_app"`
	StateReason           interface{} `json:"state_reason"`
}

type Comment struct {
	URL      string `json:"url"`
	HTMLURL  string `json:"html_url"`
	IssueURL string `json:"issue_url"`

	ID     int64  `json:"id"`
	NodeID string `json:"node_id"`

	User User `json:"user"`

	CreatedAt string `json:"created_at"`
	UpdatedAt string `json:"updated_at"`

	AuthorAssociation string `json:"author_association"`
	Body              string `json:"body"`

	Reactions Reactions `json:"reactions"`

	PerformedViaGithubApp interface{} `json:"performed_via_github_app"`
}

type User struct {
	Login      string `json:"login"`
	ID         int64  `json:"id"`
	NodeID     string `json:"node_id"`
	AvatarURL  string `json:"avatar_url"`
	GravatarID string `json:"gravatar_id"`
	URL        string `json:"url"`
	HTMLURL    string `json:"html_url"`

	FollowersURL      string `json:"followers_url"`
	FollowingURL      string `json:"following_url"`
	GistsURL          string `json:"gists_url"`
	StarredURL        string `json:"starred_url"`
	SubscriptionsURL  string `json:"subscriptions_url"`
	OrganizationsURL  string `json:"organizations_url"`
	ReposURL          string `json:"repos_url"`
	EventsURL         string `json:"events_url"`
	ReceivedEventsURL string `json:"received_events_url"`

	Type      string `json:"type"`
	SiteAdmin bool   `json:"site_admin"`
}

type Reactions struct {
	URL        string `json:"url"`
	TotalCount int    `json:"total_count"`
	PlusOne    int    `json:"+1"`
	MinusOne   int    `json:"-1"`
	Laugh      int    `json:"laugh"`
	Hooray     int    `json:"hooray"`
	Confused   int    `json:"confused"`
	Heart      int    `json:"heart"`
	Rocket     int    `json:"rocket"`
	Eyes       int    `json:"eyes"`
}

func (handler *graphqlHandler) getIssues() ([]clients.Issue, error) {
	if !strings.EqualFold(handler.repourl.commitSHA, clients.HeadSHA) {
		reponame := handler.repourl.owner + "%2F" + handler.repourl.repo
		//i assume the latest date will always be zero (always is afaik)
		date := handler.commits[0].CommittedDate.Format("2006-01-02 15:04:05")
		// get date from commit hash

		db, err := sql.Open("duckdb", "")
		if err != nil {
			return nil, fmt.Errorf("duckdb: %v", err)
		}
		defer db.Close()

		rows, err := db.Query(fmt.Sprintf(`SELECT *FROM read_parquet('/Users/adminuser/Documents/longitudinal/issue-events-partitioned-name/repo_name=%s/*.parquet')
											WHERE created_at <= '%s' ORDER BY created_at DESC`, reponame, date))

		if err != nil {
			log.Fatal(err)
		}
		defer rows.Close()

		// q := client.Query("select * from project-fe1bf1cf-ce93-4992-991.combined.c" +
		// 	" where repo_name = '" + reponame +
		// 	"' AND created_at  <= '" + date +
		// 	"' ORDER BY created_at DESC")

		// q.Location = "US"
		// job, err := q.Run(ctx)
		// if err != nil {
		// 	return nil, err
		// }
		// status, err := job.Wait(ctx)
		// if err != nil {
		// 	return nil, err
		// }
		// if err := status.Err(); err != nil {
		// 	return nil, err
		// }
		// it, err := job.Read(ctx)

		// issues := make([]clients.Issue, 30)
		issues := make(map[string]*clients.Issue)

		for rows.Next() {
			var eventType string
			var payload_str string
			var repo_id int
			var repo_name string
			var created_at_string string

			if err := rows.Scan(&eventType, &payload_str, &repo_id, &created_at_string, &repo_name); err != nil {
				log.Fatal(err)
			}
			// fmt.Print(repo_name)
			// fmt.Print(created_at_string)

			var payload WebhookPayload

			err = json.Unmarshal([]byte(payload_str), &payload)
			if err != nil {
				// panic(err)
				continue //idk what else to do. some times payload doesnt have the right fields, so we just skip those rows
			}
			// making sure its actually an issue event and not a pr event (since prs also have issues in github)
			r, _ := regexp.Compile(`https:\/\/github.com\/.*\/.*\/pull\/.*`)
			if r.MatchString(payload.Issue.HTMLURL) {
				continue
			}
			// if payload.Issue.HTMLURL
			issue, exists := issues[payload.Issue.HTMLURL]
			if !exists {
				if len(issues) >= 30 {
					continue
				}
				issue = new(clients.Issue)
				issue.URI = &payload.Issue.HTMLURL

				issue.Author = new(clients.User)
				// only Author field that is filled (even by scorecard normally)
				issue.Author.Login = payload.Issue.User.Login
				issue.AuthorAssociation = getRepoAssociation(&payload.Issue.AuthorAssociation)
				// ISO 8601 layout
				createdAt, _ := time.Parse("2006-01-02T15:04:05Z", payload.Issue.CreatedAt)
				issue.CreatedAt = &createdAt
				issues[payload.Issue.HTMLURL] = issue
			}
			if payload.Comment.URL != "" {
				comment := clients.IssueComment{}
				comment.Author = new(clients.User)
				comment.Author.Login = payload.Comment.User.Login
				comment.AuthorAssociation = getRepoAssociation(&payload.Comment.AuthorAssociation)
				// ISO 8601 layout
				createdAt, _ := time.Parse("2006-01-02T15:04:05Z", payload.Comment.CreatedAt)
				comment.CreatedAt = &createdAt
				issue.Comments = append(issue.Comments, comment)
			}
			// fmt.Println(issue)

		}
		issueSlice := make([]clients.Issue, 0, len(issues))
		for _, i := range issues {
			issueSlice = append(issueSlice, *i)
		}
		return issueSlice, nil
		// return nil, fmt.Errorf("%w: ListIssues only supported for HEAD queries", clients.ErrUnsupportedFeature)
	}
	if err := handler.setup(); err != nil {
		return nil, fmt.Errorf("error during graphqlHandler.setup: %w", err)
	}
	return handler.issues, nil
}

func (handler *graphqlHandler) isArchived() (bool, error) {
	if !strings.EqualFold(handler.repourl.commitSHA, clients.HeadSHA) {
		if handler.archivedAt.IsZero() {
			return false, nil
		}
		commitDate := handler.commits[0].CommittedDate
		return commitDate.After(handler.archivedAt), nil

		// return false, fmt.Errorf("%w: IsArchived only supported for HEAD queries", clients.ErrUnsupportedFeature)
	}
	if err := handler.setup(); err != nil {
		return false, fmt.Errorf("error during graphqlHandler.setup: %w", err)
	}
	return handler.archived, nil
}

func commitsFrom(data *graphqlData, repoOwner, repoName string) ([]clients.Commit, error) {
	ret := make([]clients.Commit, 0)
	for _, commit := range data.Repository.Object.Commit.History.Nodes {
		var committer string
		// Find the commit's committer.
		if commit.Committer.User.Login != nil && *commit.Committer.User.Login != "" {
			committer = *commit.Committer.User.Login
		} else if commit.Committer.Name != nil &&
			// Username "GitHub" may indicate the commit was committed by GitHub.
			// We verify that the commit is signed by GitHub, because the name can be spoofed.
			*commit.Committer.Name == "GitHub" &&
			commit.Signature.IsValid &&
			commit.Signature.WasSignedByGitHub {
			committer = "github"
		}

		var associatedPR clients.PullRequest
		for i := range commit.AssociatedPullRequests.Nodes {
			pr := commit.AssociatedPullRequests.Nodes[i]
			// NOTE: PR mergeCommit may not match commit.SHA in case repositories
			// have `enableSquashCommit` disabled. So we accept any associatedPR
			// to handle this case.
			if string(pr.Repository.Owner.Login) != repoOwner ||
				string(pr.Repository.Name) != repoName {
				continue
			}
			// ResourcePath: e.g., for dependabot, "/apps/dependabot", or "/apps/renovate"
			// Path that can be appended to "https://github.com" for a GitHub resource
			openedByBot := strings.HasPrefix(string(pr.Author.ResourcePath), "/apps/")
			associatedPR = clients.PullRequest{
				Number:   int(pr.Number),
				HeadSHA:  string(pr.HeadRefOid),
				MergedAt: pr.MergedAt.Time,
				Author: clients.User{
					Login: string(pr.Author.Login),
					IsBot: openedByBot,
				},
				MergedBy: clients.User{
					Login: string(pr.MergedBy.Login),
				},
			}
			for _, label := range pr.Labels.Nodes {
				associatedPR.Labels = append(associatedPR.Labels, clients.Label{
					Name: string(label.Name),
				})
			}
			for _, review := range pr.Reviews.Nodes {
				associatedPR.Reviews = append(associatedPR.Reviews, clients.Review{
					State: string(review.State),
					Author: &clients.User{
						Login: string(review.Author.Login),
					},
				})
			}
			break
		}
		ret = append(ret, clients.Commit{
			CommittedDate: commit.CommittedDate.Time,
			Message:       string(commit.Message),
			SHA:           string(commit.Oid),
			Committer: clients.User{
				Login: committer,
			},
			AssociatedMergeRequest: associatedPR,
		})
	}
	return ret, nil
}

func issuesFrom(data *graphqlData) []clients.Issue {
	var ret []clients.Issue
	for _, issue := range data.Repository.Issues.Nodes {
		var tmpIssue clients.Issue
		copyStringPtr(issue.Url, &tmpIssue.URI)
		copyRepoAssociationPtr(getRepoAssociation(issue.AuthorAssociation), &tmpIssue.AuthorAssociation)
		copyTimePtr(issue.CreatedAt, &tmpIssue.CreatedAt)
		if issue.Author.Login != "" {
			tmpIssue.Author = &clients.User{
				Login: string(issue.Author.Login),
			}
		}
		for _, comment := range issue.Comments.Nodes {
			var tmpComment clients.IssueComment
			copyRepoAssociationPtr(getRepoAssociation(comment.AuthorAssociation), &tmpComment.AuthorAssociation)
			copyTimePtr(comment.CreatedAt, &tmpComment.CreatedAt)
			if comment.Author.Login != "" {
				tmpComment.Author = &clients.User{
					Login: string(comment.Author.Login),
				}
			}
			tmpIssue.Comments = append(tmpIssue.Comments, tmpComment)
		}
		ret = append(ret, tmpIssue)
	}
	return ret
}

// getRepoAssociation returns the association of the user with the repository.
func getRepoAssociation(association *string) *clients.RepoAssociation {
	if association == nil {
		return nil
	}
	var repoAssociation clients.RepoAssociation
	switch *association {
	case "COLLABORATOR":
		repoAssociation = clients.RepoAssociationCollaborator
	case "CONTRIBUTOR":
		repoAssociation = clients.RepoAssociationContributor
	case "FIRST_TIMER":
		repoAssociation = clients.RepoAssociationFirstTimer
	case "FIRST_TIME_CONTRIBUTOR":
		repoAssociation = clients.RepoAssociationFirstTimeContributor
	case "MANNEQUIN":
		repoAssociation = clients.RepoAssociationMannequin
	case "MEMBER":
		repoAssociation = clients.RepoAssociationMember
	case "NONE":
		repoAssociation = clients.RepoAssociationNone
	case "OWNER":
		repoAssociation = clients.RepoAssociationOwner
	default:
		repoAssociation = clients.RepoAssociationMannequin
	}
	return &repoAssociation
}
