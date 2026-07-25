export type LanguageOption = {
  label: string;
  code: string;
};

export type AudioRequest = {
  text: string;
  language_code: string;
  summarize: boolean;
};

export type AudioResponse = {
  audio_url: string;
  summarized_text: string | null;
};
