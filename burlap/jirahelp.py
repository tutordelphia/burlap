import re

from fabric.api import (
    env,
    require,
    settings,
    cd,
    task,
)
from fabric.contrib import files

from burlap.common import (
    run_or_dryrun,
    put_or_dryrun,
    sudo_or_dryrun,
    local_or_dryrun,
    render_to_string,
    QueuedCommand,
)
from burlap import common
from burlap.decorators import task_or_dryrun

if 'jira_server' not in env:
    env.jira_server = None
    env.jira_basic_auth_username = None
    env.jira_basic_auth_password = None
    env.jira_update_from_git = False
    env.jira_ticket_update_message_template = 'This has been deployed to %(role)s.'
    
    # A map of status->transition to follow when making deployments.
    env.jira_deploy_workflow = {}
    
    # A map of the new-status->new-assignee to auto-assign.
    env.jira_assignee_by_status = {}
    
    # The regex used to search the commit messages for a ticket number.
    env.jira_ticket_pattern = None

@task_or_dryrun
def get_tickets_between_commits(a, b):
    from burlap.git import get_logs_between_commits
    tickets = []
    if env.jira_ticket_pattern:
        verbose = common.get_verbose()
        ret = get_logs_between_commits(a, b)
        pattern = re.compile(env.jira_ticket_pattern, flags=re.I)
        if verbose:
            print 'pattern:', env.jira_ticket_pattern
        tickets.extend(pattern.findall(ret))
    if verbose:
        print tickets
    return set(_.strip().upper() for _ in tickets)

@task_or_dryrun
def update_tickets_from_git(last=None, current=None):
    """
    Run during a deployment.
    Looks at all commits between now and the last deployment.
    Finds all ticket numbers and updates their status in Jira.
    """
    from jira import JIRA, JIRAError
    from burlap.deploy import get_last_current_diffs
    from burlap.git import get_current_commit, GIT_TRACKER
    
    dryrun = common.get_dryrun()
    verbose = common.get_verbose()
    
    # Ensure this is only run once per role.
    if env.host_string != env.hosts[-1]:
        return
    
    if not env.jira_update_from_git:
        return
    
    if not env.jira_ticket_pattern:
        return
    
    # During a deployment, we should be given these, but for testing,
    # lookup the diffs dynamically.
    if not last or not current:
        last, current = get_last_current_diffs(GIT_TRACKER)
    
    if verbose:
        print '-'*80
        print 'last.keys:', last.keys()
        print '-'*80
        print 'current.keys:', current.keys()
    
    try:
        last_commit = last['GIT_TRACKER']['current_commit']
    except KeyError:
        return
    current_commit = current['GIT_TRACKER']['current_commit']
    
    # Find all tickets deployed between last deployment and now.
    tickets = get_tickets_between_commits(current_commit, last_commit)
    if verbose:
        print 'tickets:', tickets
    
    # Update all tickets in Jira.
    jira = JIRA({
        'server': env.jira_server
    }, basic_auth=(env.jira_basic_auth_username, env.jira_basic_auth_password))
    for ticket in tickets:
        
        # Mention this Jira updated.
        comment = env.jira_ticket_update_message_template % dict(role=env.ROLE.lower())
        print 'Commenting on ticket %s: %s' % (ticket, comment)
        if not dryrun:
            jira.add_comment(ticket, comment) 
        
        # Update ticket status.
        recheck = False
        while 1:
            print 'Looking up jira ticket %s...' % ticket
            issue = jira.issue(ticket)
            print 'Ticket %s retrieved.' % ticket
            transition_to_id = dict((t['name'], t['id']) for t in jira.transitions(issue))
            print '%i allowable transitions found: %s' % (len(transition_to_id), ', '.join(transition_to_id.keys()))
#             print 'transition_to_id:', transition_to_id
#             print 'jira_deploy_workflow:', env.jira_deploy_workflow
#             print 'issue.fields.status.name:', issue.fields.status.name.title()
            next_transition_name = env.jira_deploy_workflow.get(issue.fields.status.name.title())
#             print 'next_transition_name:', next_transition_name
            next_transition_id = transition_to_id.get(next_transition_name)
#             print 'next_transition_id:', next_transition_id
            if next_transition_name:
                new_fields = {}
                
#                 print 'jira_assignee_by_status:', env.jira_assignee_by_status, issue.fields.status.name.title()
                new_assignee = env.jira_assignee_by_status.get(
                    #issue.fields.status.name.title(),
                    next_transition_name,
                    issue.fields.assignee.name,
                )
#                 print 'new_assignee:', new_assignee
                    
                print 'Updating ticket %s to status %s and assigning it to %s.' \
                    % (ticket, next_transition_name, new_assignee)
                if not dryrun:
                    jira.transition_issue(
                        issue,
                        next_transition_id,
                    )
                    
                    # Note assignment should happen after transition, since the assignment may
                    # effect remove transitions that we need.
                    try:
                        if new_assignee:
                            print 'Assigning ticket %s to %s.' % (ticket, new_assignee)
                            jira.assign_issue(issue, new_assignee)
                        else:
                            print 'No new assignee found.'
                    except JIRAError as e:
                        print>>sys.stderr, 'Unable to reassign ticket %s to %s: %s' \
                            % (ticket, new_assignee, e)
                        
                    recheck = True
            else:
                recheck = False
                print 'No transitions found for ticket %s currently in status "%s".' \
                    % (ticket, issue.fields.status.name)
                    
            if not recheck:
                break
                