const test = require("node:test");
const assert = require("node:assert/strict");
const shared = require("../src/shared.js");
const githubApiPush = import("../scripts/github-api-push.mjs");

test("normalizes common Git remote formats", () => {
  assert.equal(
    shared.normalizeRepoUrl("git@github.com:student/homework.git"),
    "https://github.com/student/homework"
  );
  assert.equal(
    shared.normalizeRepoUrl("https://gitee.com/student/homework/?tab=readme#top"),
    "https://gitee.com/student/homework"
  );
});

test("detects repository roots from supported hosting pages", () => {
  assert.equal(
    shared.repoFromPageUrl("https://github.com/student/homework/issues/2"),
    "https://github.com/student/homework"
  );
  assert.equal(
    shared.repoFromPageUrl("https://gitlab.com/team/course/homework/-/tree/main"),
    "https://gitlab.com/team/course/homework"
  );
  assert.equal(shared.repoFromPageUrl("https://example.com/student/homework"), "");
});

test("builds and reads a submission URL containing only the repository address", () => {
  const submissionUrl = shared.buildSubmissionUrl(
    "https://mn4wszvkpp.coze.site/",
    "git@github.com:student/homework.git"
  );
  assert.equal(
    shared.repoFromSubmissionUrl(submissionUrl),
    "https://github.com/student/homework"
  );
});

test("keeps identity in local settings and leaves source defaults empty", () => {
  assert.equal(shared.DEFAULT_SETTINGS.studentId, "");
  assert.equal(shared.DEFAULT_SETTINGS.name, "");
  const settings = shared.applyDefaults({
    studentId: "2026000000",
    name: "示例学生",
    autoFill: false,
    autoSubmit: false
  });
  assert.equal(settings.studentId, "2026000000");
  assert.equal(settings.name, "示例学生");
  assert.equal(settings.autoFill, true);
  assert.equal(settings.autoSubmit, true);
  assert.equal(settings.repoUrl, "");
});

test("requires identity, repository, and rendered content", () => {
  assert.equal(shared.isProfileComplete({ studentId: "1", name: "张三" }), false);
  assert.equal(
    shared.isProfileComplete({
      studentId: "2026000000",
      name: "示例学生",
      repoUrl: "https://github.com/student/homework"
    }),
    true
  );
});

test("recognizes GitHub remotes for API fallback uploads", async () => {
  const { __test } = await githubApiPush;
  assert.deepEqual(
    __test.parseGitHubRepository("git@github.com:student/homework.git"),
    { owner: "student", repo: "homework", slug: "student/homework" }
  );
  assert.equal(__test.parseGitHubRepository("https://gitee.com/student/homework.git"), null);
});

test("preserves Git timezone offsets when mirroring commits through the API", async () => {
  const { __test } = await githubApiPush;
  assert.equal(__test.offsetToIso("0", "+0800"), "1970-01-01T08:00:00+08:00");
  assert.equal(__test.offsetToIso("0", "-0500"), "1969-12-31T19:00:00-05:00");
});
