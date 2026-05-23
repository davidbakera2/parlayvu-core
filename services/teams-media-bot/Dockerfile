FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS base
WORKDIR /app
EXPOSE 8080
ENV ASPNETCORE_URLS=http://+:8080

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY src/ParlayVu.TeamsMediaBot/ParlayVu.TeamsMediaBot.csproj ParlayVu.TeamsMediaBot/
RUN dotnet restore ParlayVu.TeamsMediaBot/ParlayVu.TeamsMediaBot.csproj
COPY src/ParlayVu.TeamsMediaBot/ ParlayVu.TeamsMediaBot/
RUN dotnet publish ParlayVu.TeamsMediaBot/ParlayVu.TeamsMediaBot.csproj -c Release -o /app/publish --no-restore

FROM base AS final
WORKDIR /app
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "ParlayVu.TeamsMediaBot.dll"]
