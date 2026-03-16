import re

with open("AGENT_DELIVERY_PLAN.md", "r") as f:
    text = f.read()

text = text.replace("current_story: S3.6", "current_story: S3.7")
text = text.replace(
    "current_story_title: Automated Python Tests",
    "current_story_title: README: UX and Design Documentation",
)
text = re.sub(
    r"id: S3\.6\nepic: E9\nsprint: 3\npriority: P0\npoints: 5\nstatus: NOT_STARTED",
    r"id: S3.6\nepic: E9\nsprint: 3\npriority: P0\npoints: 5\nstatus: DONE",
    text,
)

# Update stories_done
done_match = re.search(r"stories_done: \[(.*?)\]", text)
if done_match:
    items = [x.strip() for x in done_match.group(1).split(",")]
    if "S3.6" not in items:
        items.append("S3.6")
    # Maybe clean up duplicates again just in case
    items = sorted(list(set(items)))
    text = text.replace(done_match.group(0), f"stories_done: [{', '.join(items)}]")

with open("AGENT_DELIVERY_PLAN.md", "w") as f:
    f.write(text)
