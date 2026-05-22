export type OutlookArchiveExtra = {
  label: string;
  video: string;
};

export type OutlookArchiveItem = {
  year: number;
  label: string;
  slides: string | null;
  video: string | null;
  videoStartSeconds?: number;
  extra?: OutlookArchiveExtra;
};

export const OUTLOOK_2026_VIDEO = {
  url: "https://www.youtube.com/watch?v=w-3VKXZmkso",
  label: "2026 Michigan Economic Outlook — Detroit Economic Club",
  presentedOn: "January 13, 2026",
  startSeconds: 12 * 60 + 12,
} as const;

export const OUTLOOK_ARCHIVE: OutlookArchiveItem[] = [
  {
    year: 2026,
    label: "2026 Michigan Economic Outlook — Detroit Economic Club (January 13, 2026)",
    slides: null,
    video: OUTLOOK_2026_VIDEO.url,
    videoStartSeconds: OUTLOOK_2026_VIDEO.startSeconds,
  },
  {
    year: 2023,
    label: "2023 Michigan Economic Outlook — Detroit Economic Club",
    slides:
      "https://www.outlooksurvey.com/wp-content/uploads/sites/33/2025/01/DEC-Slides-011223-2023-Michigan-Economic-Outlook-final.pdf",
    video: "https://www.youtube.com/watch?v=BgEAquk0cfY",
  },
  {
    year: 2022,
    label: "2022 Michigan Economic Outlook — Detroit Economic Club",
    slides:
      "https://www.outlooksurvey.com/wp-content/uploads/sites/33/2025/01/DEC-Slides-011322-2022-Michigan-Economic-Outlook-Final.pdf",
    video: "https://www.youtube.com/watch?v=aWGDHUWB1lY",
  },
  {
    year: 2021,
    label: "2021 Michigan Economic Outlook — Detroit Economic Club",
    slides:
      "https://www.outlooksurvey.com/wp-content/uploads/sites/33/2025/01/2021-Michigan-Economic-Outlook.pdf",
    video: null,
  },
  {
    year: 2020,
    label: "2020 Michigan Economic Outlook — Detroit Economic Club",
    slides: null,
    video: "https://www.youtube.com/watch?v=wPL7q-vgWp4",
  },
  {
    year: 2019,
    label: "2019 Economic Outlook Survey — Detroit Economic Club",
    slides: null,
    video: "https://www.youtube.com/watch?v=b4QvUMsMArk",
  },
  {
    year: 2017,
    label: "2017 Economic Outlook Survey — Detroit Economic Club",
    slides: null,
    video: "https://www.youtube.com/watch?v=YPBfkuq04O8",
  },
  {
    year: 2016,
    label: "2016 Economic Outlook Survey — Detroit Economic Club",
    slides: null,
    video: "https://www.youtube.com/watch?v=vYlAs-yrVcg",
  },
  {
    year: 2014,
    label: "2014 Economic Outlook Survey — Detroit Economic Club",
    slides: null,
    video: "https://www.youtube.com/watch?v=1jYh4dnY8Go",
    extra: {
      label: "2014 Results Discussion — Comcast Newsmakers",
      video: "https://www.youtube.com/watch?v=qphOvoy5BqE",
    },
  },
];

export const FEATURED_PARTICIPANTS = [
  "Detroit Regional Chamber",
  "Lansing Regional Chamber of Commerce",
  "Ann Arbor/Ypsilanti Regional Chamber",
  "Bay City Chamber & Agriculture",
  "Blue Water Area Chamber of Commerce",
  "Grand Rapids — The Economic Club of Grand Rapids",
  "Macomb County Chamber",
  "Southwest Michigan",
  "Michigan Works! Association",
  "Baker Strategy Group",
  "Greater Saskatoon Chamber",
  "Billings Area Chamber",
  "Indianapolis-area regional chambers",
  "Hundreds of additional chambers, CVBs, and economic development organizations",
];
